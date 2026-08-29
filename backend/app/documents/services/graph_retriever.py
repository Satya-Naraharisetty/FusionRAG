import re
from uuid import UUID

from app.documents.domain.interfaces import GraphRepository
from app.documents.domain.models import (
    AuthorizedDocumentScope,
    CanonicalIdentity,
    GraphRelationship,
    RelationshipEvidence,
    generate_entity_id,
    normalize_entity_name,
)
from app.documents.services.graph_traversal import (
    MAX_GRAPH_CANDIDATES,
    GraphTraversalService,
)


class PostgresGraphRetriever:
    def __init__(
        self,
        graph_repository: GraphRepository,
        traversal_service: GraphTraversalService | None = None,
    ) -> None:
        self.graph_repo = graph_repository
        self.traversal_service = traversal_service or GraphTraversalService(
            graph_repository
        )

    async def retrieve_candidates(
        self,
        query: str,
        scope: AuthorizedDocumentScope,
    ) -> list[tuple[CanonicalIdentity, int, RelationshipEvidence, GraphRelationship]]:
        """
        Extracts potential seed entities, traverses graph, and maps evidence to CanonicalIdentity candidates with 1-indexed ranks.
        """
        if not scope.authorized_docs or not query.strip():
            return []

        # Find potential seed entities matching query terms
        words = re.findall(r"\b[A-Za-z0-9_\-\.]{2,}\b", query)
        seed_entity_ids: list[UUID] = []

        for w in words:
            norm_name = normalize_entity_name(w)
            # Check common entity types
            for ent_type in (
                "ORGANIZATION",
                "PERSON",
                "CONCEPT",
                "PRODUCT",
                "TECHNOLOGY",
                "LOCATION",
            ):
                ent_id = generate_entity_id(scope.user_id, norm_name, ent_type)
                ent = await self.graph_repo.get_entity_by_id(scope.user_id, ent_id)
                if ent and ent.id not in seed_entity_ids:
                    seed_entity_ids.append(ent.id)

        if not seed_entity_ids:
            return []

        traversal_hits = await self.traversal_service.traverse(
            seed_entity_ids=seed_entity_ids,
            scope=scope,
        )

        candidates: list[
            tuple[CanonicalIdentity, int, RelationshipEvidence, GraphRelationship]
        ] = []
        seen_canonical: dict[CanonicalIdentity, int] = {}

        current_rank = 1
        for rel, ev, _ in traversal_hits:
            canonical_id: CanonicalIdentity = (
                ev.document_id,
                ev.document_version,
                ev.source_element_id,
            )
            # Channel-local minimum-rank deduplication
            if canonical_id not in seen_canonical:
                seen_canonical[canonical_id] = current_rank
                candidates.append((canonical_id, current_rank, ev, rel))
                current_rank += 1
                if len(candidates) >= MAX_GRAPH_CANDIDATES:
                    break

        return candidates
