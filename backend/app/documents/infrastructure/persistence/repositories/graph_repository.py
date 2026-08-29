from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.domain.interfaces import GraphRepository
from app.documents.domain.models import (
    AuthorizedDocumentScope,
    ElementStatus,
    EntityMention,
    GraphEntity,
    GraphRelationship,
    RelationshipEvidence,
)
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyDocumentElement,
    SQLAlchemyEntityMention,
    SQLAlchemyGraphEntity,
    SQLAlchemyGraphRelationship,
    SQLAlchemyRelationshipEvidence,
)


class SQLAlchemyGraphRepository(GraphRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert_entities(self, entities: list[GraphEntity]) -> list[GraphEntity]:
        persisted: list[GraphEntity] = []
        for entity in entities:
            stmt = select(SQLAlchemyGraphEntity).where(
                SQLAlchemyGraphEntity.user_id == entity.user_id,
                SQLAlchemyGraphEntity.normalized_name == entity.normalized_name,
                SQLAlchemyGraphEntity.normalized_type == entity.normalized_type,
            )
            result = await self._db.execute(stmt)
            db_ent = result.scalar_one_or_none()
            if not db_ent:
                db_ent = SQLAlchemyGraphEntity(
                    id=entity.id,
                    user_id=entity.user_id,
                    name=entity.name,
                    normalized_name=entity.normalized_name,
                    entity_type=entity.entity_type,
                    normalized_type=entity.normalized_type,
                    description=entity.description,
                    properties_json=entity.properties,
                    created_at=entity.created_at,
                    updated_at=entity.updated_at,
                )
                self._db.add(db_ent)
            else:
                if entity.description and not db_ent.description:
                    db_ent.description = entity.description
                if entity.properties:
                    current_props = db_ent.properties_json or {}
                    current_props.update(entity.properties)
                    db_ent.properties_json = current_props
                db_ent.updated_at = entity.updated_at
            await self._db.flush()
            await self._db.refresh(db_ent)
            persisted.append(self._entity_to_domain(db_ent))
        return persisted

    async def get_entity_by_id(
        self, user_id: UUID, entity_id: UUID
    ) -> GraphEntity | None:
        stmt = select(SQLAlchemyGraphEntity).where(
            SQLAlchemyGraphEntity.user_id == user_id,
            SQLAlchemyGraphEntity.id == entity_id,
        )
        result = await self._db.execute(stmt)
        db_ent = result.scalar_one_or_none()
        if not db_ent:
            return None
        return self._entity_to_domain(db_ent)

    async def save_mentions(self, mentions: list[EntityMention]) -> None:
        if not mentions:
            return
        db_mentions = [
            SQLAlchemyEntityMention(
                id=m.id,
                user_id=m.user_id,
                entity_id=m.entity_id,
                document_id=m.document_id,
                document_version=m.document_version,
                element_id=m.element_id,
                confidence=m.confidence,
                status=m.status.value if hasattr(m.status, "value") else str(m.status),
                source_span=m.source_span,
                created_at=m.created_at,
            )
            for m in mentions
        ]
        self._db.add_all(db_mentions)
        await self._db.flush()

    async def upsert_relationships(
        self, relationships: list[GraphRelationship]
    ) -> list[GraphRelationship]:
        persisted: list[GraphRelationship] = []
        for rel in relationships:
            stmt = select(SQLAlchemyGraphRelationship).where(
                SQLAlchemyGraphRelationship.user_id == rel.user_id,
                SQLAlchemyGraphRelationship.source_entity_id == rel.source_entity_id,
                SQLAlchemyGraphRelationship.normalized_relation_type
                == rel.normalized_relation_type,
                SQLAlchemyGraphRelationship.target_entity_id == rel.target_entity_id,
            )
            result = await self._db.execute(stmt)
            db_rel = result.scalar_one_or_none()
            if not db_rel:
                db_rel = SQLAlchemyGraphRelationship(
                    id=rel.id,
                    user_id=rel.user_id,
                    source_entity_id=rel.source_entity_id,
                    target_entity_id=rel.target_entity_id,
                    relation_type=rel.relation_type,
                    normalized_relation_type=rel.normalized_relation_type,
                    weight=rel.weight,
                    created_at=rel.created_at,
                    updated_at=rel.updated_at,
                )
                self._db.add(db_rel)
            else:
                db_rel.weight = max(db_rel.weight, rel.weight)
                db_rel.updated_at = rel.updated_at
            await self._db.flush()
            await self._db.refresh(db_rel)
            persisted.append(self._relationship_to_domain(db_rel))
        return persisted

    async def save_relationship_evidence(
        self, evidence_list: list[RelationshipEvidence]
    ) -> None:
        if not evidence_list:
            return
        db_evidence = [
            SQLAlchemyRelationshipEvidence(
                id=e.id,
                user_id=e.user_id,
                relationship_id=e.relationship_id,
                document_id=e.document_id,
                document_version=e.document_version,
                source_element_id=e.source_element_id,
                confidence=e.confidence,
                status=e.status.value if hasattr(e.status, "value") else str(e.status),
                source_span=e.source_span,
                created_at=e.created_at,
            )
            for e in evidence_list
        ]
        self._db.add_all(db_evidence)
        await self._db.flush()

    async def traverse_active_subgraph(
        self,
        seed_entity_ids: list[UUID],
        scope: AuthorizedDocumentScope,
        max_hops: int = 2,
        max_expansions: int = 20,
        statement_timeout_ms: int = 1000,
    ) -> list[tuple[GraphRelationship, RelationshipEvidence, int]]:
        if not seed_entity_ids or not scope.authorized_docs:
            return []

        authorized_tuples = [
            (doc_id, auth_ver.active_version)
            for doc_id, auth_ver in scope.authorized_docs.items()
            if auth_ver.active_version > 0
        ]
        if not authorized_tuples:
            return []

        # Bounded BFS traversal
        current_entity_ids = set(seed_entity_ids)
        visited_relationships: set[UUID] = set()
        results: list[tuple[GraphRelationship, RelationshipEvidence, int]] = []

        for hop in range(1, max_hops + 1):
            if not current_entity_ids or len(results) >= max_expansions:
                break

            tuple_conditions = [
                and_(
                    SQLAlchemyRelationshipEvidence.document_id == doc_id,
                    SQLAlchemyRelationshipEvidence.document_version == doc_ver,
                )
                for doc_id, doc_ver in authorized_tuples
            ]

            stmt = (
                select(
                    SQLAlchemyGraphRelationship,
                    SQLAlchemyRelationshipEvidence,
                )
                .join(
                    SQLAlchemyRelationshipEvidence,
                    and_(
                        SQLAlchemyRelationshipEvidence.relationship_id
                        == SQLAlchemyGraphRelationship.id,
                        SQLAlchemyRelationshipEvidence.user_id == scope.user_id,
                        SQLAlchemyRelationshipEvidence.status == "VALID",
                    ),
                )
                .join(
                    SQLAlchemyDocumentElement,
                    and_(
                        SQLAlchemyDocumentElement.id
                        == SQLAlchemyRelationshipEvidence.source_element_id,
                        SQLAlchemyDocumentElement.user_id == scope.user_id,
                        SQLAlchemyDocumentElement.status == "VALID",
                    ),
                )
                .where(
                    SQLAlchemyGraphRelationship.user_id == scope.user_id,
                    SQLAlchemyGraphRelationship.source_entity_id.in_(
                        current_entity_ids
                    ),
                    func.or_(*tuple_conditions),
                )
            )

            res = await self._db.execute(stmt)
            rows = res.all()

            next_entity_ids: set[UUID] = set()
            for db_rel, db_ev in rows:
                if db_rel.id not in visited_relationships:
                    visited_relationships.add(db_rel.id)
                    domain_rel = self._relationship_to_domain(db_rel)
                    domain_ev = self._evidence_to_domain(db_ev)
                    results.append((domain_rel, domain_ev, hop))
                    next_entity_ids.add(db_rel.target_entity_id)
                    if len(results) >= max_expansions:
                        break

            current_entity_ids = next_entity_ids

        return results

    def _entity_to_domain(self, db_ent: SQLAlchemyGraphEntity) -> GraphEntity:
        return GraphEntity(
            id=db_ent.id,
            user_id=db_ent.user_id,
            name=db_ent.name,
            normalized_name=db_ent.normalized_name,
            entity_type=db_ent.entity_type,
            normalized_type=db_ent.normalized_type,
            description=db_ent.description,
            properties=db_ent.properties_json or {},
            created_at=db_ent.created_at,
            updated_at=db_ent.updated_at,
        )

    def _relationship_to_domain(
        self, db_rel: SQLAlchemyGraphRelationship
    ) -> GraphRelationship:
        return GraphRelationship(
            id=db_rel.id,
            user_id=db_rel.user_id,
            source_entity_id=db_rel.source_entity_id,
            target_entity_id=db_rel.target_entity_id,
            relation_type=db_rel.relation_type,
            normalized_relation_type=db_rel.normalized_relation_type,
            weight=db_rel.weight,
            created_at=db_rel.created_at,
            updated_at=db_rel.updated_at,
        )

    def _evidence_to_domain(
        self, db_ev: SQLAlchemyRelationshipEvidence
    ) -> RelationshipEvidence:
        return RelationshipEvidence(
            id=db_ev.id,
            user_id=db_ev.user_id,
            relationship_id=db_ev.relationship_id,
            document_id=db_ev.document_id,
            document_version=db_ev.document_version,
            source_element_id=db_ev.source_element_id,
            confidence=db_ev.confidence,
            status=ElementStatus(db_ev.status),
            source_span=db_ev.source_span,
            created_at=db_ev.created_at,
        )
