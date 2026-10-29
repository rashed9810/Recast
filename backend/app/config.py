"""Runtime configuration, read from environment variables or backend/.env.

The LLM_* values are only the starting point: model settings saved from the
app (data/model.json) take priority. See app/model_config.py.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "openai" = any OpenAI-compatible server (Ollama, LM Studio, OpenAI, Groq,
    # Gemini, OpenRouter ...). "anthropic" = Claude API. "demo" = offline stub.
    llm_provider: str = "demo"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.4
    llm_max_tokens: int = 4096
    llm_timeout_seconds: float = 300.0
    llm_concurrency: int = 2

    max_input_chars: int = 60_000
    max_segment_words: int = 300
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
