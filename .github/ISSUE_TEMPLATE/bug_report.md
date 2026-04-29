---
name: Bug report
about: Something doesn't work as documented
labels: bug
---

**What you ran**
```bash
# the command(s) that failed
```

**What happened**
The actual behavior, including stack trace if any.

**What you expected**
The behavior the README / docs led you to expect.

**Environment**
- OS:
- Python:  (uv run python -V)
- LLM backend: (vLLM / Ollama / OpenAI / Anthropic / other — model name)
- Embedding backend: (model name + dim)

**`models.toml`** (with secrets redacted)
```toml
# paste the relevant role config
```

**Reproduction**
A minimal sequence of `rp` commands that reproduces the issue, or a project ID + the operation that failed.

**Anything else?**
Logs, screenshots, hypotheses about the cause.
