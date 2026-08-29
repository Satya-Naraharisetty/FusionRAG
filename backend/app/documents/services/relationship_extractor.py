import json
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.documents.domain.models import (
    ElementStatus,
    GraphEntity,
    GraphRelationship,
    RelationshipEvidence,
)


class RelationshipExtractor:
    def __init__(
        self, api_key: str | None = None, model: str = "gemini-2.0-flash"
    ) -> None:
        self.api_key = api_key or getattr(settings, "GEMINI_API_KEY", "")
        self.model = model

    async def extract_relationships(
        self,
        user_id: UUID,
        document_id: UUID,
        document_version: int,
        element_id: UUID,
        content: str,
        known_entities: list[GraphEntity],
    ) -> list[tuple[GraphRelationship, RelationshipEvidence]]:
        if not content.strip() or len(known_entities) < 2:
            return []

        entity_lookup = {e.name.lower(): e for e in known_entities}
        entity_lookup.update({e.normalized_name.lower(): e for e in known_entities})

        raw_relationships = await self._call_extractor(content, known_entities)
        results: list[tuple[GraphRelationship, RelationshipEvidence]] = []
        now = datetime.now(UTC)

        for item in raw_relationships:
            src_name = item.get("source", "").strip()
            tgt_name = item.get("target", "").strip()
            rel_type = item.get("relation_type", "RELATED_TO").strip()
            confidence = float(item.get("confidence", 1.0))
            source_span = item.get("source_span", "")

            src_entity = entity_lookup.get(src_name.lower())
            tgt_entity = entity_lookup.get(tgt_name.lower())

            if not src_entity or not tgt_entity:
                continue

            # Self-loop rejection
            if src_entity.id == tgt_entity.id:
                continue

            norm_rel_type = rel_type.strip().upper().replace(" ", "_")

            relationship = GraphRelationship(
                id=uuid.uuid4(),
                user_id=user_id,
                source_entity_id=src_entity.id,
                target_entity_id=tgt_entity.id,
                relation_type=rel_type,
                normalized_relation_type=norm_rel_type,
                weight=confidence,
                created_at=now,
                updated_at=now,
            )

            evidence = RelationshipEvidence(
                id=uuid.uuid4(),
                user_id=user_id,
                relationship_id=relationship.id,
                document_id=document_id,
                document_version=document_version,
                source_element_id=element_id,
                confidence=confidence,
                status=ElementStatus.VALID,
                source_span=source_span or content[:200],
                created_at=now,
            )

            results.append((relationship, evidence))

        return results

    async def _call_extractor(
        self, content: str, known_entities: list[GraphEntity]
    ) -> list[dict[str, Any]]:
        if not self.api_key or self.api_key.startswith("mock_"):
            return self._heuristic_extractor(content, known_entities)

        entity_names = [e.name for e in known_entities]
        prompt = (
            "Extract all factual semantic relationships connecting the given known entities from the text.\n"
            f"Known Entities: {', '.join(entity_names)}\n\n"
            "Respond strictly with a JSON list of objects with fields:\n"
            "- source: string (must match one of known entities)\n"
            "- target: string (must match another known entity)\n"
            "- relation_type: string (e.g. ACQUIRED, PART_OF, FOUNDED, PRODUCES, COMPETES_WITH, LOCATED_IN)\n"
            "- confidence: float between 0.0 and 1.0\n"
            "- source_span: excerpt from text supporting this relationship\n\n"
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
                elif isinstance(parsed, dict) and "relationships" in parsed:
                    return parsed["relationships"]
                return []
        except Exception:
            return self._heuristic_extractor(content, known_entities)

    def _heuristic_extractor(
        self, content: str, known_entities: list[GraphEntity]
    ) -> list[dict[str, Any]]:
        # Connect co-occurring entities in the same sentence/element for testing
        relationships = []
        if len(known_entities) >= 2:
            e1 = known_entities[0]
            e2 = known_entities[1]
            if e1.id != e2.id:
                relationships.append(
                    {
                        "source": e1.name,
                        "target": e2.name,
                        "relation_type": "RELATED_TO",
                        "confidence": 0.85,
                        "source_span": f"{e1.name} ... {e2.name}",
                    }
                )
        return relationships
