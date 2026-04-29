"""Probe an OpenAI-compatible endpoint.

Usage:
    pip install openai httpx
    python probe_llm.py
"""
from __future__ import annotations

import os
import sys

import httpx
from openai import OpenAI

BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:9999/v1")
API_KEY = os.environ.get("LLM_API_KEY", "sk-noop")


def list_models() -> list[str]:
    r = httpx.get(f"{BASE_URL}/models", headers={"Authorization": f"Bearer {API_KEY}"}, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", [])
    return [m["id"] for m in data]


def chat(model: str) -> str:
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a terse assistant."},
            {"role": "user", "content": "Reply with exactly: PROBE_OK"},
        ],
        max_tokens=16,
        temperature=0,
    )
    return resp.choices[0].message.content or ""


def main() -> int:
    print(f"[probe] base_url = {BASE_URL}")
    try:
        models = list_models()
    except Exception as e:
        print(f"[probe] /models failed: {e}")
        return 2

    if not models:
        print("[probe] endpoint returned empty model list")
        return 2

    print(f"[probe] models available ({len(models)}):")
    for m in models[:10]:
        print(f"        - {m}")
    if len(models) > 10:
        print(f"        ... {len(models) - 10} more")

    model = os.environ.get("LLM_MODEL", models[0])
    print(f"[probe] testing chat with model: {model}")
    try:
        out = chat(model)
    except Exception as e:
        print(f"[probe] chat failed: {e}")
        return 3

    print(f"[probe] response: {out!r}")
    ok = "PROBE_OK" in out
    print(f"[probe] {'PASS' if ok else 'WEAK PASS (response off, but endpoint is live)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
