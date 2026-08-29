from app.documents.domain.interfaces import GraphRepository
from app.documents.domain.models import (
    EntityMention,
    GraphEntity,
    GraphRelationship,
    RelationshipEvidence,
)


class KnowledgeGraphService:
    def __init__(self, graph_repository: GraphRepository) -> None:
        self.graph_repo = graph_repository

    async def ingest_triples(
        self,
        entities: list[GraphEntity],
        mentions: list[EntityMention],
        relationships: list[GraphRelationship],
        evidence_list: list[RelationshipEvidence],
    ) -> None:
        if entities:
            await self.graph_repo.upsert_entities(entities)
        if mentions:
            await self.graph_repo.save_mentions(mentions)
        if relationships:
            await self.graph_repo.upsert_relationships(relationships)
        if evidence_list:
            await self.graph_repo.save_relationship_evidence(evidence_list)
