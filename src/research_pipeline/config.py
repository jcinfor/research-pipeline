"""Load role-keyed LLM model config from models.toml.

Resolution order:
    1. path passed to load_config(path=...)
    2. $RP_MODELS_TOML
    3. ./models.toml (cwd)
    4. ~/.research-pipeline/models.toml
    5. poc/models.toml (dev fallback)
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_path


@dataclass(frozen=True)
class RoleConfig:
    backend: str
    base_url: str
    api_key_env: str
    model: str

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "sk-noop")


@dataclass(frozen=True)
class Config:
    roles: dict[str, RoleConfig]
    source: Path

    def role(self, name: str) -> RoleConfig:
        if name not in self.roles:
            raise KeyError(
                f"Role {name!r} not defined in {self.source}. "
                f"Known roles: {sorted(self.roles)}"
            )
        return self.roles[name]


def _candidate_paths(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    paths: list[Path] = []
    env = os.environ.get("RP_MODELS_TOML")
    if env:
        paths.append(Path(env))
    paths.append(Path.cwd() / "models.toml")
    paths.append(user_config_path("research-pipeline", appauthor=False) / "models.toml")
    paths.append(Path(__file__).resolve().parents[2] / "poc" / "models.toml")
    return paths


def load_config(path: Path | None = None) -> Config:
    for candidate in _candidate_paths(path):
        if candidate.exists():
            with candidate.open("rb") as f:
                raw = tomllib.load(f)
            roles = {
                name: RoleConfig(**cfg)
                for name, cfg in raw.get("roles", {}).items()
            }
            if not roles:
                raise ValueError(f"No [roles.*] entries in {candidate}")
            return Config(roles=roles, source=candidate)
    raise FileNotFoundError(
        "No models.toml found. Set RP_MODELS_TOML or create ./models.toml. "
        f"Searched: {[str(p) for p in _candidate_paths(path)]}"
    )
