"""Document ingestion: PDF/DOCX/PPTX/HTML/etc. -> markdown -> blackboard evidence.

We use Microsoft's MarkItDown for the conversion, chunk the output, and file
each chunk as a `kind=evidence` entry with `agent_id=NULL` (so the dashboard
shows it as a PI / system contribution, not an agent's claim). Each chunk
gets embedded so agents can retrieve it through the existing retrieval path.

Phase 3: deterministically hash-partition 20% of chunks into `visibility='held_out'`
so PGR Proxy 2 has a held-out set to check claims against. Agents never see
held-out chunks (retrieval filters them); only PGR scoring reads them.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .adapter import LLMClient
from .blackboard import KIND_EVIDENCE
from .dedup import add_entry_with_dedup
from .promote import extract_refs


HELD_OUT_FRACTION = 0.2  # 20% of chunks become held-out for PGR proxy


def _is_held_out(content: str, fraction: float = HELD_OUT_FRACTION) -> bool:
    """Deterministic: same content -> same bucket across runs."""
    h = hashlib.sha256(content.encode("utf-8")).digest()
    # Use first 4 bytes as an int in [0, 2^32)
    n = int.from_bytes(h[:4], "big")
    return (n / 0xFFFFFFFF) < fraction


@dataclass
class IngestResult:
    file: str
    chunks: int
    added: int
    echoed: int
    held_out: int = 0


def ingest_file(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    path: Path,
    work_dir: Path,
    llm: LLMClient | None = None,
    chunk_max_chars: int = 1600,
    chunk_min_chars: int = 400,
    dedup_threshold: float = 0.95,
) -> IngestResult:
    """Convert `path` to markdown via MarkItDown, chunk, and file each chunk
    as a blackboard evidence entry embedded via the adapter's `embedding` role.
    """
    # Late import so the `rp` CLI loads without markitdown installed.
    from markitdown import MarkItDown

    md = MarkItDown()
    result = md.convert(str(path))
    content = (result.text_content or "").strip()
    if not content:
        return IngestResult(file=path.name, chunks=0, added=0, echoed=0)

    raw_dir = work_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{path.stem}.md").write_text(content, encoding="utf-8")

    chunks = _chunk_markdown(
        content, max_chars=chunk_max_chars, min_chars=chunk_min_chars
    )

    added = 0
    echoed = 0
    held_out = 0
    for chunk in chunks:
        refs = [f"source={path.name}"] + extract_refs(chunk)
        visibility = "held_out" if _is_held_out(chunk) else "visible"
        _, was_dedup, _ = add_entry_with_dedup(
            conn,
            project_id=project_id,
            kind=KIND_EVIDENCE,
            content=chunk,
            turn=0,
            agent_id=None,
            refs=refs,
            llm=llm,
            threshold=dedup_threshold,
        )
        if was_dedup:
            echoed += 1
            continue
        added += 1
        if visibility == "held_out":
            # The dedup insert created the row with default visibility='visible';
            # flip the most-recent row for this content to held_out.
            conn.execute(
                "UPDATE blackboard_entries SET visibility = 'held_out' "
                "WHERE project_id = ? AND content = ? "
                "AND id = (SELECT MAX(id) FROM blackboard_entries "
                "          WHERE project_id = ? AND content = ?)",
                (project_id, chunk, project_id, chunk),
            )
            held_out += 1
    conn.commit()

    return IngestResult(
        file=path.name, chunks=len(chunks), added=added, echoed=echoed,
        held_out=held_out,
    )


def _chunk_markdown(
    text: str, *, max_chars: int, min_chars: int
) -> list[str]:
    """Split markdown into retrieval-sized chunks.

    Strategy:
        1. Split by heading boundaries (#, ##, ###, ...).
        2. For oversized sections, split by blank-line paragraphs.
        3. Merge undersized chunks into the previous chunk.
    """
    text = text.strip()
    if not text:
        return []

    # Split on heading boundaries while keeping the heading with its section.
    sections = re.split(r"\n(?=#{1,6} )", text)
    chunks: list[str] = []

    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= max_chars:
            if chunks and len(section) < min_chars:
                chunks[-1] = chunks[-1] + "\n\n" + section
            else:
                chunks.append(section)
            continue

        # Section too big — split by paragraph
        current = ""
        for para in re.split(r"\n\s*\n", section):
            para = para.strip()
            if not para:
                continue
            if current and len(current) + len(para) + 2 > max_chars:
                chunks.append(current)
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current:
            chunks.append(current)

    return chunks
