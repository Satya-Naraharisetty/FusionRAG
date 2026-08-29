from uuid import UUID

from app.documents.domain.interfaces import GraphRepository
from app.documents.domain.models import (
    AuthorizedDocumentScope,
    GraphRelationship,
    RelationshipEvidence,
)

MAX_GRAPH_HOPS: int = 2
MAX_GRAPH_SEEDS: int = 5
MAX_GRAPH_EXPANSIONS: int = 20
MAX_GRAPH_CANDIDATES: int = 50
GRAPH_STATEMENT_TIMEOUT_MS: int = 1000


class GraphTraversalService:
    def __init__(self, graph_repo: GraphRepository) -> None:
        self.graph_repo = graph_repo

    async def traverse(
        self,
        seed_entity_ids: list[UUID],
        scope: AuthorizedDocumentScope,
        max_hops: int = MAX_GRAPH_HOPS,
        max_expansions: int = MAX_GRAPH_EXPANSIONS,
        statement_timeout_ms: int = GRAPH_STATEMENT_TIMEOUT_MS,
    ) -> list[tuple[GraphRelationship, RelationshipEvidence, int]]:
        limited_seeds = seed_entity_ids[:MAX_GRAPH_SEEDS]
        if not limited_seeds:
            return []

        raw_results = await self.graph_repo.traverse_active_subgraph(
            seed_entity_ids=limited_seeds,
            scope=scope,
            max_hops=max_hops,
            max_expansions=max_expansions,
            statement_timeout_ms=statement_timeout_ms,
        )

        # Deterministic 7-tuple sort:
        # (hop_distance ASC, evidence_confidence DESC, relationship_weight DESC,
        #  document_id ASC, document_version ASC, element_id ASC, relationship_id ASC)
        def sort_key(
            item: tuple[GraphRelationship, RelationshipEvidence, int],
        ) -> tuple:
            rel, ev, hop = item
            return (
                hop,
                -ev.confidence,
                -rel.weight,
                str(ev.document_id),
                ev.document_version,
                str(ev.source_element_id),
                str(rel.id),
            )

        sorted_results = sorted(raw_results, key=sort_key)
        return sorted_results[:MAX_GRAPH_CANDIDATES]
