from pathlib import Path

from research_pipeline.config import load_config


def test_load_poc_config():
    poc = Path(__file__).resolve().parents[1] / "poc" / "models.toml"
    cfg = load_config(poc)
    assert "planner" in cfg.roles
    planner = cfg.role("planner")
    assert planner.backend == "openai-compatible"
    assert planner.base_url.startswith("http")
    assert planner.model
