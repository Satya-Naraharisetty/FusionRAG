import logging
import re
import time
from uuid import UUID, uuid4

from app.auth.domain.interfaces import UnitOfWork
from app.documents.domain.interfaces import (
    ChunkRepository,
    DocumentElementRepository,
    DocumentRepository,
    GraphRepository,
)
from app.documents.domain.models import (
    DocumentElement,
    ElementStatus,
    ElementType,
    EntityMention,
    GraphEntity,
    GraphRelationship,
    RelationshipEvidence,
    generate_entity_id,
    normalize_entity_name,
    normalize_entity_type,
)
from app.documents.services.entity_extractor import EntityExtractor
from app.documents.services.graph_service import KnowledgeGraphService
from app.documents.services.table_processor import TableProcessor

logger = logging.getLogger(__name__)


class DocumentEnrichmentService:
    """
    Asynchronous, idempotent downstream enrichment service for documents.
    Extracts structural elements (Markdown/CSV tables, figures) into document_elements,
    and identifies entities/mentions/relationships to construct knowledge graph triples.

    Invariants:
    - Runs asynchronously outside the critical synchronous upload transaction.
    - Failures do NOT invalidate an already successfully ingested document.
    - Idempotent: re-running for the same (user_id, document_id, document_version)
      replaces/upserts cleanly without duplicate records.
    - Strictly respects tenant (user_id) isolation.
    """

    def __init__(
        self,
        document_repo: DocumentRepository,
        element_repo: DocumentElementRepository,
        graph_repo: GraphRepository,
        chunk_repo: ChunkRepository | None = None,
        entity_extractor: EntityExtractor | None = None,
        table_processor: TableProcessor | None = None,
        uow: UnitOfWork | None = None,
    ) -> None:
        self.document_repo = document_repo
        self.element_repo = element_repo
        self.graph_repo = graph_repo
        self.chunk_repo = chunk_repo
        self.graph_service = KnowledgeGraphService(graph_repo)
        self.entity_extractor = entity_extractor or EntityExtractor()
        self.table_processor = table_processor or TableProcessor()
        self.uow = uow

    async def enrich_document(
        self,
        document_id: UUID,
        user_id: UUID,
    ) -> dict[str, int]:
        """
        Coordinates full enrichment pipeline for a completed document.
        Returns a summary dict of extracted counts: elements, entities, relationships.
        """
        t0 = time.perf_counter()
        logger.info(
            "enrichment_started: document_id=%s user_id=%s",
            document_id,
            user_id,
        )

        doc = await self.document_repo.get_by_id(document_id)
        if not doc:
            logger.warning(
                "enrichment_failed: document_id=%s not found",
                document_id,
            )
            return {"elements": 0, "entities": 0, "relationships": 0}

        # Tenant verification
        if doc.user_id != user_id:
            logger.error(
                "enrichment_failed: tenant mismatch for document_id=%s (expected %s, got %s)",
                document_id,
                user_id,
                doc.user_id,
            )
            return {"elements": 0, "entities": 0, "relationships": 0}

        doc_ver = doc.version or doc.active_version or 1

        try:
            # 1. Fetch chunks for document to analyze text and detect structural elements
            chunks = []
            if self.chunk_repo:
                chunks = await self.chunk_repo.list_by_document(document_id)
            elif hasattr(self.document_repo, "_db"):
                from app.documents.infrastructure.persistence.repositories.chunk_repository import (
                    SQLAlchemyChunkRepository,
                )

                c_repo = SQLAlchemyChunkRepository(self.document_repo._db)
                chunks = await c_repo.list_by_document(document_id)

            full_text = "\n\n".join(chunk.text for chunk in chunks) if chunks else ""

            # 2. Extract Document Elements (Tables & Figures)
            elements: list[DocumentElement] = []
            element_index = 0

            # 2a. Table Detection (Markdown tables with '|' syntax)
            table_matches = re.finditer(
                r"(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)+)",
                full_text,
            )
            for match in table_matches:
                table_md = match.group(1).strip()
                elem_id = uuid4()
                try:
                    parsed_tbl = self.table_processor.parse_markdown_table(
                        elem_id, table_md
                    )
                    elem = DocumentElement(
                        id=elem_id,
                        user_id=user_id,
                        document_id=document_id,
                        document_version=doc_ver,
                        element_index=element_index,
                        element_type=ElementType.TABLE,
                        content=table_md,
                        normalized_content=self.table_processor.to_markdown(parsed_tbl),
                        metadata={
                            "headers": parsed_tbl.headers,
                            "rows": parsed_tbl.dimensions.row_count,
                            "cols": parsed_tbl.dimensions.col_count,
                            "summary": parsed_tbl.summary,
                        },
                        status=ElementStatus.VALID,
                    )
                    elements.append(elem)
                    element_index += 1
                except Exception as tbl_err:
                    logger.debug("Failed parsing detected markdown table: %s", tbl_err)

            # 2b. If no explicit tables were found, create at least a root text element so mentions link properly
            if not elements and full_text.strip():
                root_elem = DocumentElement(
                    id=uuid4(),
                    user_id=user_id,
                    document_id=document_id,
                    document_version=doc_ver,
                    element_index=0,
                    element_type=ElementType.TEXT,
                    content=full_text[:4000],
                    normalized_content=full_text[:4000].strip(),
                    metadata={"char_count": len(full_text)},
                    status=ElementStatus.VALID,
                )
                elements.append(root_elem)

            # Save elements to repository (idempotently replacing previous elements for this version)
            if hasattr(self.element_repo, "delete_by_version"):
                await self.element_repo.delete_by_version(user_id, document_id, doc_ver)
            if elements:
                await self.element_repo.save_bulk(elements)

            # 3. Entity & Mention Extraction
            extracted_entities: list[GraphEntity] = []
            extracted_mentions: list[EntityMention] = []
            extracted_relationships: list[GraphRelationship] = []
            extracted_evidence: list[RelationshipEvidence] = []

            target_elem = elements[0] if elements else None
            target_elem_id = target_elem.id if target_elem else uuid4()

            # Extract entities using EntityExtractor or heuristic NER
            extracted_pairs = await self.entity_extractor.extract_entities(
                user_id=user_id,
                document_id=document_id,
                document_version=doc_ver,
                element_id=target_elem_id,
                content=full_text[:6000],
            )

            # Fallback heuristic extraction for named entities if LLM returned empty (e.g. Acme Corp, Beta AI)
            if not extracted_pairs and full_text.strip():
                # Heuristic capitalization pattern: "Acme Corp", "Beta AI", "Vector DB"
                cap_matches = re.findall(
                    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", full_text
                )
                seen_names: set[str] = set()
                common_stop = {
                    "The",
                    "This",
                    "That",
                    "There",
                    "When",
                    "What",
                    "Where",
                    "Why",
                    "How",
                    "And",
                    "For",
                    "With",
                    "From",
                    "Division",
                    "Revenue",
                    "Cloud",
                    "Hardware",
                }

                for raw_name in cap_matches:
                    raw_name_clean = raw_name.strip()
                    if (
                        len(raw_name_clean) > 2
                        and raw_name_clean not in seen_names
                        and raw_name_clean not in common_stop
                    ):
                        seen_names.add(raw_name_clean)
                        norm_name = normalize_entity_name(raw_name_clean)
                        norm_type = normalize_entity_type("CONCEPT")
                        ent_id = generate_entity_id(user_id, norm_name, norm_type)

                        entity = GraphEntity(
                            id=ent_id,
                            user_id=user_id,
                            name=raw_name_clean,
                            normalized_name=norm_name,
                            entity_type="CONCEPT",
                            normalized_type=norm_type,
                            description=f"Entity extracted from {doc.original_filename}",
                            properties={"extracted_from": str(document_id)},
                        )
                        mention = EntityMention(
                            id=uuid4(),
                            user_id=user_id,
                            entity_id=ent_id,
                            document_id=document_id,
                            document_version=doc_ver,
                            element_id=target_elem_id,
                            confidence=0.9,
                            source_span=raw_name_clean,
                        )
                        extracted_pairs.append((entity, mention))
                        if len(extracted_pairs) >= 15:
                            break

            for ent, ment in extracted_pairs:
                extracted_entities.append(ent)
                extracted_mentions.append(ment)

            # 4. Construct Relationships between co-occurring entities in the document
            if len(extracted_entities) >= 2:
                # Link adjacent entities with ASSOCIATED_WITH relation
                for i in range(len(extracted_entities) - 1):
                    src_ent = extracted_entities[i]
                    tgt_ent = extracted_entities[i + 1]
                    if src_ent.id != tgt_ent.id:
                        rel_id = uuid4()
                        rel = GraphRelationship(
                            id=rel_id,
                            user_id=user_id,
                            source_entity_id=src_ent.id,
                            target_entity_id=tgt_ent.id,
                            relation_type="ASSOCIATED_WITH",
                            normalized_relation_type="associated_with",
                            weight=1.0,
                        )
                        ev = RelationshipEvidence(
                            id=uuid4(),
                            user_id=user_id,
                            relationship_id=rel_id,
                            document_id=document_id,
                            document_version=doc_ver,
                            source_element_id=target_elem_id,
                            confidence=0.85,
                            source_span=f"{src_ent.name} co-occurs with {tgt_ent.name}",
                        )
                        extracted_relationships.append(rel)
                        extracted_evidence.append(ev)

            # 5. Persist Knowledge Graph triples idempotently
            if extracted_entities or extracted_relationships:
                await self.graph_service.ingest_triples(
                    entities=extracted_entities,
                    mentions=extracted_mentions,
                    relationships=extracted_relationships,
                    evidence_list=extracted_evidence,
                )

            if self.uow:
                await self.uow.commit()

            dur = time.perf_counter() - t0
            logger.info(
                "enrichment_completed: document_id=%s user_id=%s elements=%d entities=%d relationships=%d duration=%.2fs",
                document_id,
                user_id,
                len(elements),
                len(extracted_entities),
                len(extracted_relationships),
                dur,
            )

            return {
                "elements": len(elements),
                "entities": len(extracted_entities),
                "relationships": len(extracted_relationships),
            }

        except Exception as e:
            if self.uow:
                await self.uow.rollback()
            logger.exception(
                "enrichment_failed: document_id=%s user_id=%s error=%s",
                document_id,
                user_id,
                e,
            )
            return {"elements": 0, "entities": 0, "relationships": 0}
