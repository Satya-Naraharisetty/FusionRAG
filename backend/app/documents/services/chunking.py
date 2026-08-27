import re
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
        parent_chunk_size: int = 1500,
        parent_chunk_overlap: int = 150,
        child_chunk_size: int = 400,
        child_chunk_overlap: int = 50,
        sentence_window_size: int = 2,
        enable_parent_child: bool = False,
        enable_sentence_window: bool = False,
        enable_contextual: bool = False,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.strategy = strategy
        self.parent_chunk_size = parent_chunk_size
        self.parent_chunk_overlap = parent_chunk_overlap
        self.child_chunk_size = child_chunk_size
        self.child_chunk_overlap = child_chunk_overlap
        self.sentence_window_size = max(1, sentence_window_size)
        self.enable_parent_child = enable_parent_child or (strategy == "parent_child")
        self.enable_sentence_window = enable_sentence_window or (
            strategy == "sentence_window"
        )
        self.enable_contextual = enable_contextual or (strategy == "contextual")
        self.separators = ["\n\n", "\n", " ", ""]

    def chunk_document(
        self,
        text: str,
        document_id: uuid.UUID,
        checksum: str | None = None,
        document_name: str | None = None,
    ) -> ChunkResult:
        """
        Splits a cleaned document text into logical chunks.
        Supports standard recursive chunking, hierarchical parent-child chunking,
        sentence-window chunking, and contextual enrichment.
        """
        if not text.strip():
            return ChunkResult(chunks=[])

        if self.enable_parent_child:
            return self._chunk_parent_child(
                text=text,
                document_id=document_id,
                checksum=checksum,
                document_name=document_name,
            )
        elif self.enable_sentence_window:
            return self._chunk_sentence_window(
                text=text,
                document_id=document_id,
                checksum=checksum,
                document_name=document_name,
            )
        else:
            return self._chunk_recursive(
                text=text,
                document_id=document_id,
                checksum=checksum,
                document_name=document_name,
            )

    def _chunk_recursive(
        self,
        text: str,
        document_id: uuid.UUID,
        checksum: str | None = None,
        document_name: str | None = None,
    ) -> ChunkResult:
        raw_pieces = self._split_text(
            text, 0, self.separators, target_size=self.chunk_size
        )

        chunks_temp: list[tuple[str, int, int]] = []
        current_chunk_pieces: list[tuple[str, int]] = []
        current_length = 0

        for piece, start_idx in raw_pieces:
            piece_len = len(piece)
            estimated_added_len = piece_len + (1 if current_chunk_pieces else 0)
            if current_length + estimated_added_len <= self.chunk_size:
                current_chunk_pieces.append((piece, start_idx))
                current_length += estimated_added_len
            else:
                if current_chunk_pieces:
                    start_pos = current_chunk_pieces[0][1]
                    end_pos = current_chunk_pieces[-1][1] + len(
                        current_chunk_pieces[-1][0]
                    )
                    chunk_text = text[start_pos:end_pos]
                    chunks_temp.append((chunk_text, start_pos, end_pos))

                overlap_pieces: list[tuple[str, int]] = []
                overlap_len = 0
                for p, s in reversed(current_chunk_pieces):
                    p_len = len(p)
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

        if current_chunk_pieces:
            start_pos = current_chunk_pieces[0][1]
            end_pos = current_chunk_pieces[-1][1] + len(current_chunk_pieces[-1][0])
            chunk_text = text[start_pos:end_pos]
            chunks_temp.append((chunk_text, start_pos, end_pos))

        filtered_chunks: list[Chunk] = []
        for chunk_text, start, end in chunks_temp:
            if len(chunks_temp) > 1 and len(chunk_text) < self.min_chunk_size:
                continue

            token_est = max(1, len(chunk_text) // 4)
            chunk_idx = len(filtered_chunks)

            if checksum:
                chunk_uuid = uuid.uuid5(document_id, f"{checksum}:{chunk_idx}")
            else:
                chunk_uuid = uuid.uuid5(document_id, f"chunk_{chunk_idx}")

            metadata: dict = {}
            if self.enable_contextual and document_name:
                metadata["contextual_text"] = (
                    f"[Document: {document_name}]\n{chunk_text}"
                )

            filtered_chunks.append(
                Chunk(
                    id=chunk_uuid,
                    document_id=document_id,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    character_start=start,
                    character_end=end,
                    token_estimate=token_est,
                    metadata=metadata,
                    created_at=datetime.now(UTC),
                )
            )

        return ChunkResult(chunks=filtered_chunks)

    def _chunk_parent_child(
        self,
        text: str,
        document_id: uuid.UUID,
        checksum: str | None = None,
        document_name: str | None = None,
    ) -> ChunkResult:
        parent_pieces = self._split_text(
            text, 0, self.separators, target_size=self.parent_chunk_size
        )
        parents_temp: list[tuple[str, int, int]] = []
        curr_pieces: list[tuple[str, int]] = []
        curr_len = 0

        for piece, start_idx in parent_pieces:
            piece_len = len(piece)
            est_len = piece_len + (1 if curr_pieces else 0)
            if curr_len + est_len <= self.parent_chunk_size:
                curr_pieces.append((piece, start_idx))
                curr_len += est_len
            else:
                if curr_pieces:
                    start_pos = curr_pieces[0][1]
                    end_pos = curr_pieces[-1][1] + len(curr_pieces[-1][0])
                    parents_temp.append((text[start_pos:end_pos], start_pos, end_pos))

                ov_pieces: list[tuple[str, int]] = []
                ov_len = 0
                for p, s in reversed(curr_pieces):
                    p_len = len(p)
                    est_ov = p_len + (1 if ov_pieces else 0)
                    if ov_len + est_ov <= self.parent_chunk_overlap:
                        ov_pieces.insert(0, (p, s))
                        ov_len += est_ov
                    else:
                        break
                curr_pieces = ov_pieces
                curr_pieces.append((piece, start_idx))
                curr_len = sum(len(p) for p, _ in curr_pieces) + (len(curr_pieces) - 1)

        if curr_pieces:
            start_pos = curr_pieces[0][1]
            end_pos = curr_pieces[-1][1] + len(curr_pieces[-1][0])
            parents_temp.append((text[start_pos:end_pos], start_pos, end_pos))

        child_chunks: list[Chunk] = []
        total_child_idx = 0

        for p_idx, (p_text, p_start, _p_end) in enumerate(parents_temp):
            if checksum:
                parent_id = uuid.uuid5(document_id, f"{checksum}:parent_{p_idx}")
            else:
                parent_id = uuid.uuid5(document_id, f"parent_{p_idx}")

            child_raw = self._split_text(
                p_text, 0, self.separators, target_size=self.child_chunk_size
            )
            c_temp: list[tuple[str, int, int]] = []
            c_curr_pieces: list[tuple[str, int]] = []
            c_curr_len = 0

            for piece, start_idx in child_raw:
                piece_len = len(piece)
                est_len = piece_len + (1 if c_curr_pieces else 0)
                if c_curr_len + est_len <= self.child_chunk_size:
                    c_curr_pieces.append((piece, start_idx))
                    c_curr_len += est_len
                else:
                    if c_curr_pieces:
                        s_pos = c_curr_pieces[0][1]
                        e_pos = c_curr_pieces[-1][1] + len(c_curr_pieces[-1][0])
                        c_temp.append((p_text[s_pos:e_pos], s_pos, e_pos))

                    ov_pieces = []
                    ov_len = 0
                    for p, s in reversed(c_curr_pieces):
                        p_len = len(p)
                        est_ov = p_len + (1 if ov_pieces else 0)
                        if ov_len + est_ov <= self.child_chunk_overlap:
                            ov_pieces.insert(0, (p, s))
                            ov_len += est_ov
                        else:
                            break
                    c_curr_pieces = ov_pieces
                    c_curr_pieces.append((piece, start_idx))
                    c_curr_len = sum(len(p) for p, _ in c_curr_pieces) + (
                        len(c_curr_pieces) - 1
                    )

            if c_curr_pieces:
                s_pos = c_curr_pieces[0][1]
                e_pos = c_curr_pieces[-1][1] + len(c_curr_pieces[-1][0])
                c_temp.append((p_text[s_pos:e_pos], s_pos, e_pos))

            for c_in_p_idx, (c_text, c_start_rel, c_end_rel) in enumerate(c_temp):
                if len(c_temp) > 1 and len(c_text) < self.min_chunk_size:
                    continue

                abs_start = p_start + c_start_rel
                abs_end = p_start + c_end_rel
                token_est = max(1, len(c_text) // 4)

                if checksum:
                    child_id = uuid.uuid5(
                        document_id, f"{checksum}:p{p_idx}_c{c_in_p_idx}"
                    )
                else:
                    child_id = uuid.uuid5(document_id, f"chunk_{total_child_idx}")

                meta = {
                    "parent_chunk_id": str(parent_id),
                    "parent_chunk_index": p_idx,
                    "parent_text": p_text,
                    "child_index_in_parent": c_in_p_idx,
                    "chunk_type": "child",
                }
                if self.enable_contextual and document_name:
                    meta["contextual_text"] = f"[Document: {document_name}]\n{c_text}"

                child_chunks.append(
                    Chunk(
                        id=child_id,
                        document_id=document_id,
                        chunk_index=total_child_idx,
                        text=c_text,
                        character_start=abs_start,
                        character_end=abs_end,
                        token_estimate=token_est,
                        metadata=meta,
                        created_at=datetime.now(UTC),
                    )
                )
                total_child_idx += 1

        return ChunkResult(chunks=child_chunks)

    def _chunk_sentence_window(
        self,
        text: str,
        document_id: uuid.UUID,
        checksum: str | None = None,
        document_name: str | None = None,
    ) -> ChunkResult:
        sentence_matches = list(
            re.finditer(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s+", text)
        )

        sentences: list[tuple[str, int, int]] = []
        prev_end = 0
        for match in sentence_matches:
            s_text = text[prev_end : match.start()].strip()
            if s_text:
                sentences.append((s_text, prev_end, match.start()))
            prev_end = match.end()

        if prev_end < len(text):
            s_text = text[prev_end:].strip()
            if s_text:
                sentences.append((s_text, prev_end, len(text)))

        if not sentences:
            sentences = [(text.strip(), 0, len(text))]

        chunks: list[Chunk] = []
        w_size = self.sentence_window_size

        for i, (s_text, start, end) in enumerate(sentences):
            w_start_idx = max(0, i - w_size)
            w_end_idx = min(len(sentences), i + w_size + 1)
            window_parts = [sentences[j][0] for j in range(w_start_idx, w_end_idx)]
            window_text = " ".join(window_parts)

            token_est = max(1, len(s_text) // 4)

            if checksum:
                chunk_uuid = uuid.uuid5(document_id, f"{checksum}:sent_{i}")
            else:
                chunk_uuid = uuid.uuid5(document_id, f"sent_{i}")

            meta = {
                "chunk_type": "sentence_window",
                "sentence_index": i,
                "total_sentences": len(sentences),
                "window_size": w_size,
                "window_text": window_text,
            }
            if self.enable_contextual and document_name:
                meta["contextual_text"] = f"[Document: {document_name}]\n{s_text}"

            chunks.append(
                Chunk(
                    id=chunk_uuid,
                    document_id=document_id,
                    chunk_index=i,
                    text=s_text,
                    character_start=start,
                    character_end=end,
                    token_estimate=token_est,
                    metadata=meta,
                    created_at=datetime.now(UTC),
                )
            )

        return ChunkResult(chunks=chunks)

    def _split_text(
        self,
        text: str,
        offset: int,
        separators: list[str],
        target_size: int | None = None,
    ) -> list[tuple[str, int]]:
        max_sz = target_size or self.chunk_size
        if len(text) <= max_sz or not separators:
            return [(text, offset)]

        separator = separators[0]
        next_separators = separators[1:]

        if separator == "":
            return [
                (text[i : i + max_sz], offset + i) for i in range(0, len(text), max_sz)
            ]

        splits: list[tuple[str, int]] = []
        parts = text.split(separator)
        current_offset = 0

        for part in parts:
            part_pos = current_offset
            current_offset += len(part) + len(separator)

            if not part:
                continue

            if len(part) > max_sz:
                splits.extend(
                    self._split_text(
                        part, offset + part_pos, next_separators, target_size=max_sz
                    )
                )
            else:
                splits.append((part, offset + part_pos))

        return splits
