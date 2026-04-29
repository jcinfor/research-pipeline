from pathlib import Path

import pytest

from research_pipeline.ingest import _chunk_markdown


def test_chunk_preserves_heading_sections():
    md = "# Intro\n\nHello world.\n\n## Methods\n\nWe did stuff.\n\n## Results\n\nIt worked."
    chunks = _chunk_markdown(md, max_chars=200, min_chars=20)
    # Each heading starts a new chunk
    assert any(c.startswith("# Intro") for c in chunks)
    assert any(c.startswith("## Methods") for c in chunks)
    assert any(c.startswith("## Results") for c in chunks)


def test_chunk_splits_long_sections():
    # A section with 10 paragraphs, each ~80 chars -> must split
    paras = [f"Paragraph {i} with some meaningful content about the topic." for i in range(10)]
    md = "## Long section\n\n" + "\n\n".join(paras)
    chunks = _chunk_markdown(md, max_chars=300, min_chars=100)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 450  # soft cap; allows a little slop when merging


def test_chunk_merges_small_sections():
    md = "# Tiny\n\nShort.\n\n# Also tiny\n\nBrief."
    chunks = _chunk_markdown(md, max_chars=400, min_chars=100)
    # Two tiny sections merged into one chunk
    assert len(chunks) == 1
    assert "Tiny" in chunks[0] and "Also tiny" in chunks[0]


def test_empty_input():
    assert _chunk_markdown("", max_chars=100, min_chars=10) == []
    assert _chunk_markdown("   \n\n   ", max_chars=100, min_chars=10) == []


def test_ingest_file_roundtrip(tmp_path: Path):
    """Smoke test: MarkItDown can ingest a plain .txt and file chunks."""
    from research_pipeline.blackboard import KIND_EVIDENCE, list_entries
    from research_pipeline.db import connect, init_db
    from research_pipeline.ingest import ingest_file
    from research_pipeline.projects import create_project, upsert_user

    # Create a simple markdown source
    src = tmp_path / "note.md"
    src.write_text(
        "# Background\n\nKRAS G12C is a driver mutation in NSCLC.\n\n"
        "## Prior art\n\nSotorasib and adagrasib are covalent inhibitors. "
        "Resistance emerges via secondary mutations.\n\n"
        "## Open questions\n\nCan non-covalent inhibitors bypass resistance?",
        encoding="utf-8",
    )

    db = tmp_path / "rp.db"
    init_db(db)
    with connect(db) as conn:
        uid = upsert_user(conn, "u@x")
        pid = create_project(
            conn, user_id=uid, goal="test",
            archetype_ids=["scout", "hypogen", "critic"],
        )
        # llm=None skips embedding, which keeps this test offline/fast
        res = ingest_file(conn, project_id=pid, path=src, work_dir=tmp_path,
                          llm=None)
        entries = list_entries(conn, pid, kind=KIND_EVIDENCE)

    assert res.chunks >= 1
    assert res.added >= 1
    assert len(entries) >= 1
    # refs should carry the source filename
    assert any("source=note.md" in (r if isinstance(r, str) else "") for e in entries for r in e.refs)
