"""Provider-agnostic LLM adapter.

All LLM traffic in the app goes through LLMClient.chat(role=...).
The role name keys into models.toml; any OpenAI-compatible endpoint works.
"""
from __future__ import annotations

from functools import cache
from typing import Any

from openai import AsyncOpenAI, OpenAI

from .config import Config, RoleConfig, load_config


class LLMClient:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config()

    @cache  # type: ignore[misc]
    def _sync(self, role: str) -> OpenAI:
        rc = self.config.role(role)
        return OpenAI(base_url=rc.base_url, api_key=rc.api_key)

    @cache  # type: ignore[misc]
    def _async(self, role: str) -> AsyncOpenAI:
        rc = self.config.role(role)
        return AsyncOpenAI(base_url=rc.base_url, api_key=rc.api_key)

    def role_info(self, role: str) -> RoleConfig:
        return self.config.role(role)

    def chat(
        self,
        role: str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> Any:
        rc = self.config.role(role)
        kwargs: dict[str, Any] = {"model": rc.model, "messages": messages}
        if tools is not None:
            kwargs["tools"] = tools
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature
        if response_format is not None:
            kwargs["response_format"] = response_format
        return self._sync(role).chat.completions.create(**kwargs)

    async def achat(
        self,
        role: str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> Any:
        rc = self.config.role(role)
        kwargs: dict[str, Any] = {"model": rc.model, "messages": messages}
        if tools is not None:
            kwargs["tools"] = tools
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature
        if response_format is not None:
            kwargs["response_format"] = response_format
        return await self._async(role).chat.completions.create(**kwargs)

    def embed(self, role: str, texts: list[str] | str) -> list[list[float]]:
        """Embed one or many strings via the role's embedding endpoint."""
        rc = self.config.role(role)
        if isinstance(texts, str):
            texts = [texts]
        resp = self._sync(role).embeddings.create(model=rc.model, input=texts)
        return [d.embedding for d in resp.data]

    async def aembed(self, role: str, texts: list[str] | str) -> list[list[float]]:
        rc = self.config.role(role)
        if isinstance(texts, str):
            texts = [texts]
        resp = await self._async(role).embeddings.create(model=rc.model, input=texts)
        return [d.embedding for d in resp.data]
