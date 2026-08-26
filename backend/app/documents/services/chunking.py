import uuid
from datetime import UTC, datetime

from app.documents.domain.models import Chunk, ChunkResult


class ChunkingService:
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
        strategy: str = "recursive",
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.strategy = strategy
        self.separators = ["\n\n", "\n", " ", ""]

    def chunk_document(
        self, text: str, document_id: uuid.UUID, checksum: str | None = None
    ) -> ChunkResult:
        """
        Splits a cleaned document text into logical chunks.
        Applies a recursive character splitting algorithm with standard separators.
        Generates deterministic, version-aware chunk UUIDs if checksum is provided.
        """
        if not text.strip():
            return ChunkResult(chunks=[])

        # Recursively split the text by separators
        raw_pieces = self._split_text(text, 0, self.separators)

        chunks_temp: list[tuple[str, int, int]] = []
        current_chunk_pieces: list[tuple[str, int]] = []
        current_length = 0

        for piece, start_idx in raw_pieces:
            piece_len = len(piece)

            # If current piece + existing pieces fits in the chunk budget
            # We add 1 to current_length if current_chunk_pieces is not empty, representing space or separator length
            estimated_added_len = piece_len + (1 if current_chunk_pieces else 0)
            if current_length + estimated_added_len <= self.chunk_size:
                current_chunk_pieces.append((piece, start_idx))
                current_length += estimated_added_len
            else:
                # Emit the current chunk
                if current_chunk_pieces:
                    start_pos = current_chunk_pieces[0][1]
                    end_pos = current_chunk_pieces[-1][1] + len(
                        current_chunk_pieces[-1][0]
                    )
                    chunk_text = text[start_pos:end_pos]
                    chunks_temp.append((chunk_text, start_pos, end_pos))

                # Backtrack to build the overlap
                overlap_pieces: list[tuple[str, int]] = []
                overlap_len = 0
                for p, s in reversed(current_chunk_pieces):
                    p_len = len(p)
                    # Try to fit the piece into the overlap size budget
                    estimated_overlap_added = p_len + (1 if overlap_pieces else 0)
                    if overlap_len + estimated_overlap_added <= self.chunk_overlap:
                        overlap_pieces.insert(0, (p, s))
                        overlap_len += estimated_overlap_added
                    else:
                        break

                current_chunk_pieces = overlap_pieces
                current_chunk_pieces.append((piece, start_idx))
                current_length = sum(len(p) for p, _ in current_chunk_pieces) + (
                    len(current_chunk_pieces) - 1
                )

        # Emit the final remaining pieces
        if current_chunk_pieces:
            start_pos = current_chunk_pieces[0][1]
            end_pos = current_chunk_pieces[-1][1] + len(current_chunk_pieces[-1][0])
            chunk_text = text[start_pos:end_pos]
            chunks_temp.append((chunk_text, start_pos, end_pos))

        # Map to domain Chunk structures
        filtered_chunks: list[Chunk] = []
        for chunk_text, start, end in chunks_temp:
            # Enforce min_chunk_size only if there are multiple chunks
            if len(chunks_temp) > 1 and len(chunk_text) < self.min_chunk_size:
                continue

            # Heuristic: approx_tokens = characters / 4
            token_est = max(1, len(chunk_text) // 4)
            chunk_idx = len(filtered_chunks)

            # Deterministic, version-aware chunk UUID
            if checksum:
                chunk_uuid = uuid.uuid5(document_id, f"{checksum}:{chunk_idx}")
            else:
                chunk_uuid = uuid.uuid5(document_id, f"chunk_{chunk_idx}")

            filtered_chunks.append(
                Chunk(
                    id=chunk_uuid,
                    document_id=document_id,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    character_start=start,
                    character_end=end,
                    token_estimate=token_est,
                    metadata={},  # reserved for page number, heading, section, table, image references, semantic labels (future)
                    created_at=datetime.now(UTC),
                )
            )

        return ChunkResult(chunks=filtered_chunks)

    def _split_text(
        self, text: str, offset: int, separators: list[str]
    ) -> list[tuple[str, int]]:
        """
        Recursively splits text on separators, tracking character offsets.
        """
        if len(text) <= self.chunk_size or not separators:
            return [(text, offset)]

        separator = separators[0]
        next_separators = separators[1:]

        if separator == "":
            # Character splitter fallback
            return [
                (text[i : i + self.chunk_size], offset + i)
                for i in range(0, len(text), self.chunk_size)
            ]

        splits: list[tuple[str, int]] = []
        parts = text.split(separator)
        current_offset = 0

        for part in parts:
            part_pos = current_offset
            # Update current offset for next iteration (include separator length)
            current_offset += len(part) + len(separator)

            if not part:
                continue

            if len(part) > self.chunk_size:
                splits.extend(
                    self._split_text(part, offset + part_pos, next_separators)
                )
            else:
                splits.append((part, offset + part_pos))

        return splits
