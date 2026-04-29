"""Phase-2 POC: one agent, one Twitter turn, driven by a local vLLM Gemma.

Validates that OASIS accepts a custom OpenAI-compat base_url and that the
model can complete the agent-action selection prompt end-to-end.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import traceback
from pathlib import Path

from camel.models import ModelFactory
from camel.types import ModelPlatformType

import oasis
from oasis import (
    ActionType,
    LLMAction,
    ManualAction,
    generate_twitter_agent_graph,
)

POC_DIR = Path(__file__).parent
DB_PATH = (POC_DIR / "oasis_poc.db").resolve()
PROFILE_CSV = (POC_DIR / "mini_profile.csv").resolve()

BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:9999/v1")
API_KEY = os.environ.get("LLM_API_KEY", "sk-noop")
MODEL = os.environ.get("LLM_MODEL", "google/gemma-4-26B-A4B-it")


async def main() -> int:
    os.environ["OASIS_DB_PATH"] = str(DB_PATH)
    if DB_PATH.exists():
        DB_PATH.unlink()

    print(f"[poc2] base_url = {BASE_URL}")
    print(f"[poc2] model    = {MODEL}")
    print(f"[poc2] profile  = {PROFILE_CSV}")

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=MODEL,
        api_key=API_KEY,
        url=BASE_URL,
        model_config_dict={"temperature": 0.2, "max_tokens": 512},
    )

    agent_graph = await generate_twitter_agent_graph(
        profile_path=str(PROFILE_CSV),
        model=model,
        available_actions=ActionType.get_default_twitter_actions(),
    )
    print("[poc2] agent_graph built")

    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.TWITTER,
        database_path=str(DB_PATH),
    )
    await env.reset()
    print("[poc2] env reset ok")

    agent0 = env.agent_graph.get_agent(0)

    print("[poc2] step 1 (ManualAction CREATE_POST) ...")
    await env.step({agent0: ManualAction(
        action_type=ActionType.CREATE_POST,
        action_args={"content": "POC: hello from research-pipeline!"},
    )})
    print("[poc2] step 1 OK")

    print("[poc2] step 2 (LLMAction via Gemma) ...")
    llm_ok = False
    try:
        await env.step({agent0: LLMAction()})
        llm_ok = True
        print("[poc2] step 2 OK")
    except Exception as e:
        print(f"[poc2] step 2 FAILED: {e.__class__.__name__}: {e}")
        traceback.print_exc()

    await env.close()

    conn = sqlite3.connect(DB_PATH)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )]
        print(f"[poc2] sqlite tables: {tables}")
        for t in tables:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"[poc2]   {t:24s} {n} rows")
            except Exception as e:
                print(f"[poc2]   {t:24s} err: {e}")
    finally:
        conn.close()

    print(f"[poc2] {'PASS' if llm_ok else 'PARTIAL (Manual OK, LLM failed)'}")
    return 0 if llm_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
