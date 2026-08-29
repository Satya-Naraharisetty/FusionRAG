import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.documents.domain.models import (
    ElementStatus,
    EntityMention,
    GraphEntity,
    generate_entity_id,
    normalize_entity_name,
    normalize_entity_type,
)


class EntityExtractor:
    def __init__(
        self, api_key: str | None = None, model: str = "gemini-2.0-flash"
    ) -> None:
        self.api_key = api_key or getattr(settings, "GEMINI_API_KEY", "")
        self.model = model

    async def extract_entities(
        self,
        user_id: UUID,
        document_id: UUID,
        document_version: int,
        element_id: UUID,
        content: str,
    ) -> list[tuple[GraphEntity, EntityMention]]:
        if not content.strip():
            return []

        extracted_raw = await self._call_extractor(content)
        results: list[tuple[GraphEntity, EntityMention]] = []
        now = datetime.now(UTC)

        for item in extracted_raw:
            raw_name = item.get("name", "").strip()
            raw_type = item.get("type", "CONCEPT").strip()
            confidence = float(item.get("confidence", 1.0))
            source_span = item.get("source_span", raw_name)

            if not raw_name:
                continue

            norm_name = normalize_entity_name(raw_name)
            norm_type = normalize_entity_type(raw_type)

            entity_id = generate_entity_id(user_id, norm_name, norm_type)

            entity = GraphEntity(
                id=entity_id,
                user_id=user_id,
                name=raw_name,
                normalized_name=norm_name,
                entity_type=raw_type,
                normalized_type=norm_type,
                description=item.get("description"),
                properties=item.get("properties", {}),
                created_at=now,
                updated_at=now,
            )

            mention = EntityMention(
                id=entity_id,  # Deterministic mention linkage
                user_id=user_id,
                entity_id=entity_id,
                document_id=document_id,
                document_version=document_version,
                element_id=element_id,
                confidence=confidence,
                status=ElementStatus.VALID,
                source_span=source_span,
                created_at=now,
            )

            results.append((entity, mention))

        return results

    async def _call_extractor(self, content: str) -> list[dict[str, Any]]:
        if not self.api_key or self.api_key.startswith("mock_"):
            return self._heuristic_extractor(content)

        prompt = (
            "Extract all named entities (organizations, persons, products, concepts, metrics) from the following text.\n"
            "Respond strictly with a JSON list of objects with fields:\n"
            "- name: string\n"
            "- type: string (e.g. ORGANIZATION, PERSON, PRODUCT, CONCEPT, METRIC)\n"
            "- confidence: float between 0.0 and 1.0\n"
            "- source_span: exact substring match in text\n"
            "- description: short description if evident\n\n"
            f"Text:\n{content}"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_out)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict) and "entities" in parsed:
                    return parsed["entities"]
                return []
        except Exception:
            return self._heuristic_extractor(content)

    def _heuristic_extractor(self, content: str) -> list[dict[str, Any]]:
        # Heuristic extraction of capitalized words & acronyms for offline/mock testing
        entities = []
        words = re.findall(
            r"\b[A-Z][a-zA-Z0-9_\-\.]+(?:\s+[A-Z][a-zA-Z0-9_\-\.]+)*\b", content
        )
        seen = set()
        for word in words:
            if (
                word in seen
                or len(word) < 2
                or word.lower() in ("the", "this", "that", "there", "and", "for")
            ):
                continue
            seen.add(word)
            ent_type = (
                "ORGANIZATION"
                if any(
                    s in word.lower()
                    for s in (
                        "inc",
                        "corp",
                        "llc",
                        "ltd",
                        "google",
                        "apple",
                        "microsoft",
                    )
                )
                else "CONCEPT"
            )
            entities.append(
                {
                    "name": word,
                    "type": ent_type,
                    "confidence": 0.9,
                    "source_span": word,
                }
            )
        return entities
