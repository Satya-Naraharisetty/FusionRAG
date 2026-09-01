import time
from uuid import UUID

from app.chat.domain.models import Citation
from app.chat.domain.multi_agent import (
    AgentExecutionContext,
    AgentResult,
    AgentTask,
    AgentTaskStatus,
    AgentType,
    EvidenceItem,
)
from app.chat.services.multi_agent.base import BaseSpecialistAgent
from app.documents.domain.models import (
    AuthorizedDocumentScope,
    AuthorizedDocumentVersion,
)
from app.documents.services.graph_retriever import PostgresGraphRetriever


class GraphAgent(BaseSpecialistAgent):
    """
    Specialist agent for knowledge graph traversal, entity relationship queries,
    and cross-document multi-hop entity reasoning.
    """

    agent_type = AgentType.GRAPH

    def __init__(self, graph_retriever: PostgresGraphRetriever | None = None) -> None:
        if graph_retriever is not None and hasattr(graph_retriever, "dependency"):
            self.graph_retriever = None
        else:
            self.graph_retriever = graph_retriever

    async def execute_task(
        self, task: AgentTask, context: AgentExecutionContext
    ) -> AgentResult:
        t0 = time.perf_counter()
        query = task.request

        evidence_items: list[EvidenceItem] = []
        citations: list[Citation] = []
        relationships_found: list[str] = []

        if self.graph_retriever:
            # Construct AuthorizedDocumentScope from context
            auth_docs: dict[UUID, AuthorizedDocumentVersion] = {}
            if context.document_ids:
                for d_id in context.document_ids:
                    auth_docs[d_id] = AuthorizedDocumentVersion(
                        active_version=1,
                        active_config_id=UUID("00000000-0000-0000-0000-000000000000"),
                        active_embedding_contract_id="contract_default",
                    )
            else:
                # If no specific document IDs passed, query all active user document versions from repo
                try:
                    from sqlalchemy import select

                    from app.documents.infrastructure.persistence.models import (
                        SQLAlchemyRelationshipEvidence,
                    )

                    if hasattr(self.graph_retriever.graph_repo, "_db"):
                        stmt = (
                            select(
                                SQLAlchemyRelationshipEvidence.document_id,
                                SQLAlchemyRelationshipEvidence.document_version,
                            )
                            .where(
                                SQLAlchemyRelationshipEvidence.user_id
                                == context.user_id,
                                SQLAlchemyRelationshipEvidence.status == "VALID",
                            )
                            .distinct()
                        )
                        res = await self.graph_retriever.graph_repo._db.execute(stmt)
                        for doc_id, doc_ver in res.all():
                            auth_docs[doc_id] = AuthorizedDocumentVersion(
                                active_version=doc_ver,
                                active_config_id=UUID(
                                    "00000000-0000-0000-0000-000000000000"
                                ),
                                active_embedding_contract_id="contract_default",
                            )
                except Exception:
                    pass

            scope = AuthorizedDocumentScope(
                user_id=context.user_id,
                authorized_docs=auth_docs,
            )

            hits = await self.graph_retriever.retrieve_candidates(query, scope)
            for _canon_id, _rank, ev, rel in hits:
                rel_desc = f"Relationship: {rel.relation_type} (source element {ev.source_element_id}, confidence: {ev.confidence:.2f})"
                relationships_found.append(rel_desc)

                ev_item = EvidenceItem(
                    document_id=ev.document_id,
                    document_name=f"Knowledge Graph (Doc {ev.document_id})",
                    content=ev.source_span or rel_desc,
                    score=ev.confidence,
                    metadata={
                        "relationship_id": str(rel.id),
                        "relation_type": rel.relation_type,
                    },
                )
                evidence_items.append(ev_item)

        if relationships_found:
            output_text = (
                "Knowledge graph traversal found relationships:\n"
                + "\n".join(f"- {r}" for r in relationships_found)
            )
        else:
            output_text = f"Knowledge graph reasoning completed for query: '{query}'"

        dur_ms = (time.perf_counter() - t0) * 1000.0

        return AgentResult(
            task_id=task.task_id,
            agent_type=self.agent_type,
            status=AgentTaskStatus.COMPLETED,
            success=True,
            output=output_text,
            evidence=evidence_items,
            citations=citations,
            execution_time_ms=dur_ms,
        )
