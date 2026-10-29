"""The active model configuration, editable from the app.

Starts from environment variables (backend/.env). When the user saves
settings in the app, they are written to ``<data dir>/model.json`` and win
over the environment from then on. Delete that file to go back to .env.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .config import Settings

ProviderKind = Literal["openai", "anthropic", "demo"]


class ModelConfig(BaseModel):
    provider: ProviderKind = "demo"
    preset: str = "demo"  # which preset the UI shows; informational only
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = Field(0.4, ge=0.0, le=1.5)
    concurrency: int = Field(2, ge=1, le=8)
    timeout_seconds: float = Field(300.0, ge=10, le=1800)
    max_tokens: int = Field(4096, ge=256, le=32000)

    def public(self) -> dict:
        """Safe to send to the browser: the key is never returned."""
        d = self.model_dump(exclude={"api_key"})
        d["has_key"] = bool(self.api_key)
        d["key_hint"] = f"…{self.api_key[-4:]}" if len(self.api_key) >= 8 else ""
        return d


_ALIASES = {
    "openai-compatible": "openai", "ollama": "openai", "lmstudio": "openai", "openrouter": "openai",
    "groq": "openai", "vllm": "openai", "gemini": "openai", "claude": "anthropic",
}


def data_dir() -> Path:
    d = Path(os.environ.get("RECAST_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _from_env(s: Settings) -> ModelConfig:
    kind = s.llm_provider.strip().lower()
    preset = kind if kind in _ALIASES or kind in {"openai", "anthropic", "demo"} else "custom"
    if "11434" in s.llm_base_url:
        preset = "ollama"
    return ModelConfig(
        provider=_ALIASES.get(kind, kind) if _ALIASES.get(kind, kind) in {"openai", "anthropic", "demo"} else "demo",
        preset=preset,
        base_url=s.llm_base_url,
        api_key=s.llm_api_key,
        model=s.llm_model,
        temperature=s.llm_temperature,
        concurrency=s.llm_concurrency,
        timeout_seconds=s.llm_timeout_seconds,
        max_tokens=s.llm_max_tokens,
    )


def load(s: Settings) -> ModelConfig:
    path = data_dir() / "model.json"
    if path.exists():
        try:
            return ModelConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass  # a broken file falls back to .env rather than crashing
    return _from_env(s)


def save(cfg: ModelConfig) -> None:
    path = data_dir() / "model.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg.model_dump(), indent=2), encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)  # the file holds an API key
    except OSError:
        pass
