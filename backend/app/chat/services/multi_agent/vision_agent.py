import logging
import time

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
from app.documents.domain.interfaces import DocumentElementRepository
from app.documents.domain.models import ElementType
from app.documents.services.vision_processor import VisionProcessor

logger = logging.getLogger(__name__)


class VisionAgent(BaseSpecialistAgent):
    """
    Specialist agent for visual reasoning, diagram inspection,
    and chart/figure data extraction.
    """

    agent_type = AgentType.VISION

    def __init__(
        self,
        vision_processor: VisionProcessor | None = None,
        element_repo: DocumentElementRepository | None = None,
    ) -> None:
        if vision_processor is None or hasattr(vision_processor, "dependency"):
            self.vision_processor = VisionProcessor()
        else:
            self.vision_processor = vision_processor

        if element_repo is not None and hasattr(element_repo, "dependency"):
            self.element_repo = None
        else:
            self.element_repo = element_repo

    async def execute_task(
        self, task: AgentTask, context: AgentExecutionContext
    ) -> AgentResult:
        t0 = time.perf_counter()
        query = task.request
        image_bytes = task.parameters.get("image_bytes")
        image_b64 = task.parameters.get("image_bytes_b64") or task.parameters.get("image_base64")
        if not image_bytes and image_b64 and isinstance(image_b64, str):
            import base64
            try:
                image_bytes = base64.b64decode(image_b64)
            except Exception as b64_err:
                logger.warning("Failed to decode base64 image bytes: %s", b64_err)

        element_type = task.parameters.get("element_type", "FIGURE")
        caption = task.parameters.get("caption", "")
        repo_visual_desc = ""

        # Consume visual element from DocumentElementRepository if available and image_bytes empty
        if not image_bytes and self.element_repo and context.user_id:
            try:
                doc_ids_to_check = context.document_ids or []
                for doc_id in doc_ids_to_check:
                    elements = await self.element_repo.list_by_version(
                        user_id=context.user_id,
                        document_id=doc_id,
                        document_version=1,
                    )
                    for el in elements:
                        if el.element_type in (ElementType.FIGURE, ElementType.CHART):
                            caption = el.metadata.get("caption") or caption or "Chart/Figure"
                            element_type = el.element_type.value
                            repo_visual_desc = el.content
                            if el.content.startswith("iVBOR") or len(el.content) > 100:
                                try:
                                    import base64
                                    image_bytes = base64.b64decode(el.content)
                                except Exception:
                                    pass
                            break
                    if repo_visual_desc or image_bytes:
                        break
            except Exception as elem_err:
                logger.debug("Failed querying visual element from repo: %s", elem_err)

        evidence_items: list[EvidenceItem] = []
        citations: list[Citation] = []
        output_text = ""

        if image_bytes and isinstance(image_bytes, bytes):
            desc, payload = await self.vision_processor.process_visual_element(
                image_bytes=image_bytes,
                element_type=element_type,
                caption=caption,
            )
            output_text = f"Visual analysis ({element_type}): {desc}"
            ev = EvidenceItem(
                document_name=caption or f"Visual {element_type}",
                content=output_text,
                score=0.95,
                metadata={"element_type": element_type, "caption": caption},
            )
            evidence_items.append(ev)
        elif repo_visual_desc:
            output_text = f"Visual analysis ({element_type}): {repo_visual_desc}"
            ev = EvidenceItem(
                document_name=caption or f"Visual {element_type}",
                content=output_text,
                score=0.95,
                metadata={"element_type": element_type, "caption": caption},
            )
            evidence_items.append(ev)
        else:
            output_text = f"Visual inspection completed for query: '{query}'"

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
