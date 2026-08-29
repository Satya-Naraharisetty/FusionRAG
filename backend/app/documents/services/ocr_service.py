import base64
import io

import httpx

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]

from app.core.config import settings
from app.documents.domain.exceptions import DocumentCorrupted, UnsupportedDocumentType
from app.documents.domain.interfaces import OCRProvider

MAX_IMAGE_PIXELS = 89_478_485  # Decompression bomb safety threshold (~89.5 MP)


def validate_image_bytes(image_bytes: bytes) -> tuple[int, int, str]:
    if len(image_bytes) < 4:
        raise DocumentCorrupted("Image file payload too small to contain valid header.")

    # Magic byte check
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        mime_type = "image/png"
    elif image_bytes.startswith(b"\xff\xd8\xff"):
        mime_type = "image/jpeg"
    elif image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        mime_type = "image/gif"
    elif image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
        mime_type = "image/webp"
    elif image_bytes.startswith(b"%PDF"):
        mime_type = "application/pdf"
    else:
        raise UnsupportedDocumentType(
            "File fails magic-byte validation for supported image/document formats."
        )

    if mime_type.startswith("image/"):
        if Image is not None:
            try:
                with Image.open(io.BytesIO(image_bytes)) as img:
                    width, height = img.size
                    num_pixels = width * height
                    if num_pixels > MAX_IMAGE_PIXELS:
                        raise DocumentCorrupted(
                            f"Image resolution {width}x{height} ({num_pixels} pixels) exceeds safe limit of {MAX_IMAGE_PIXELS} pixels (decompression bomb protection)."
                        )
                    return width, height, mime_type
            except Exception as e:
                if isinstance(e, (DocumentCorrupted, UnsupportedDocumentType)):
                    raise
                raise DocumentCorrupted(f"Failed to decode image: {str(e)}")
        return 0, 0, mime_type

    return 0, 0, mime_type


class MockOCRProvider(OCRProvider):
    async def extract_text_from_image(self, image_bytes: bytes) -> str:
        validate_image_bytes(image_bytes)
        return "Sample OCR extracted text from document image."


class GeminiOCRProvider(OCRProvider):
    def __init__(
        self, api_key: str | None = None, model: str = "gemini-2.0-flash"
    ) -> None:
        self.api_key = api_key or getattr(settings, "GEMINI_API_KEY", "")
        self.model = model

    async def extract_text_from_image(self, image_bytes: bytes) -> str:
        width, height, mime_type = validate_image_bytes(image_bytes)

        if not self.api_key or self.api_key.startswith("mock_"):
            return "OCR text: Scanned page containing financial summary and account balances."

        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Extract all text present in this image verbatim. Do not summarize or alter formatting."
                        },
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.0},
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


class OCRService:
    def __init__(self, provider: OCRProvider | None = None) -> None:
        self.provider = provider or MockOCRProvider()

    async def extract_text(self, image_bytes: bytes) -> str:
        return await self.provider.extract_text_from_image(image_bytes)
