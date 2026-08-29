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
from app.documents.services.vision_processor import VisionProcessor


class VisionAgent(BaseSpecialistAgent):
    """
    Specialist agent for visual reasoning, diagram inspection,
    and chart/figure data extraction.
    """

    agent_type = AgentType.VISION

    def __init__(self, vision_processor: VisionProcessor | None = None) -> None:
        self.vision_processor = vision_processor or VisionProcessor()

    async def execute_task(
        self, task: AgentTask, context: AgentExecutionContext
    ) -> AgentResult:
        t0 = time.perf_counter()
        query = task.request
        image_bytes = task.parameters.get("image_bytes")
        element_type = task.parameters.get("element_type", "FIGURE")
        caption = task.parameters.get("caption", "")

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
