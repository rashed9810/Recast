from __future__ import annotations

from ..model_config import ModelConfig
from .anthropic import AnthropicProvider
from .base import LLMProvider, ProviderError
from .demo import DemoProvider
from .openai_compat import OpenAICompatProvider

__all__ = ["LLMProvider", "ProviderError", "build_provider"]


def build_provider(c: ModelConfig) -> LLMProvider:
    if c.provider == "openai":
        if not c.base_url.strip():
            raise ProviderError("A server address is required.")
        return OpenAICompatProvider(c.base_url, c.api_key, c.model, c.temperature, c.max_tokens, c.timeout_seconds)
    if c.provider == "anthropic":
        base = c.base_url if "anthropic" in c.base_url else None
        return AnthropicProvider(c.api_key, c.model, c.temperature, c.max_tokens, c.timeout_seconds, base)
    if c.provider == "demo":
        return DemoProvider()
    raise ProviderError(f"Unknown provider '{c.provider}'.")
