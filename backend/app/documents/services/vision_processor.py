import base64

import httpx

from app.core.config import settings
from app.documents.domain.interfaces import VisionProvider
from app.documents.domain.models import format_visual_embedding_payload
from app.documents.services.ocr_service import validate_image_bytes


class MockVisionProvider(VisionProvider):
    async def describe_visual_element(
        self,
        image_bytes: bytes,
        element_type: str = "FIGURE",
        prompt: str | None = None,
    ) -> str:
        validate_image_bytes(image_bytes)
        if element_type == "CHART":
            return "Bar chart showing quarterly revenue growth from Q1 2023 ($10M) to Q4 2023 ($18M), trending upward."
        elif element_type == "TABLE":
            return "Financial table detailing balance sheet assets, liabilities, and equity for FY2023."
        return "Architectural diagram depicting a multi-tier microservices application with API gateway and message queue."


class GeminiVisionProvider(VisionProvider):
    def __init__(
        self, api_key: str | None = None, model: str = "gemini-2.0-flash"
    ) -> None:
        self.api_key = api_key or getattr(settings, "GEMINI_API_KEY", "")
        self.model = model

    async def describe_visual_element(
        self,
        image_bytes: bytes,
        element_type: str = "FIGURE",
        prompt: str | None = None,
    ) -> str:
        width, height, mime_type = validate_image_bytes(image_bytes)

        if not self.api_key or self.api_key.startswith("mock_"):
            mock = MockVisionProvider()
            return await mock.describe_visual_element(image_bytes, element_type, prompt)

        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        default_prompt = (
            f"Analyze this {element_type} in detail. Describe its structural composition, key entities, "
            f"numerical metrics, trends, axis labels, legends, and relevant conclusions."
        )
        instruction = prompt or default_prompt

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": instruction},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.1},
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                return "".join(p.get("text", "") for p in parts).strip()
            return ""


class VisionProcessor:
    def __init__(self, provider: VisionProvider | None = None) -> None:
        self.provider = provider or MockVisionProvider()

    async def process_visual_element(
        self,
        image_bytes: bytes,
        element_type: str = "FIGURE",
        caption: str = "",
        extracted_data: str = "",
    ) -> tuple[str, str]:
        """
        Processes an image/chart/figure, returns (visual_description, formatted_embedding_payload).
        """
        description = await self.provider.describe_visual_element(
            image_bytes, element_type=element_type
        )
        payload = format_visual_embedding_payload(
            element_type=element_type,
            caption=caption,
            visual_description=description,
            extracted_data=extracted_data,
        )
        return description, payload
