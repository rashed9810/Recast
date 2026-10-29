"""Anthropic Messages API (Claude models)."""

from __future__ import annotations

import httpx

from .base import LLMProvider, ProviderError, friendly_http_error, is_retryable_status

API_BASE = "https://api.anthropic.com"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int,
                 timeout: float, base_url: str | None = None) -> None:
        if not api_key:
            raise ProviderError("An API key is required for Anthropic. Add it in Model setup.")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.send_temperature = True
        self.base = (base_url or API_BASE).rstrip("/").removesuffix("/v1")
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )

    async def _complete(self, system: str, user: str, temperature: float | None) -> str:
        if not self.model:
            raise ProviderError("No model selected. Choose one in Model setup.")
        for _ in range(2):
            payload: dict = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
            if self.send_temperature:
                payload["temperature"] = self.temperature if temperature is None else temperature
            try:
                r = await self.client.post(f"{self.base}/v1/messages", json=payload)
            except httpx.TimeoutException as e:
                raise ProviderError("The Anthropic API took too long to answer.", retryable=True) from e
            except httpx.HTTPError as e:
                raise ProviderError(f"Could not reach the Anthropic API: {e.__class__.__name__}") from e
            if r.status_code == 400 and "temperature" in r.text.lower() and self.send_temperature:
                self.send_temperature = False
                continue
            if r.status_code >= 400:
                raise ProviderError(friendly_http_error("The Anthropic API", r.status_code, r.text),
                                    retryable=is_retryable_status(r.status_code))
            data = r.json()
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        raise ProviderError("The Anthropic API rejected the request parameters.")

    async def list_models(self) -> list[str]:
        try:
            r = await self.client.get(f"{self.base}/v1/models", params={"limit": 100})
        except httpx.HTTPError as e:
            raise ProviderError("Could not reach the Anthropic API.") from e
        if r.status_code >= 400:
            raise ProviderError(friendly_http_error("The Anthropic API", r.status_code, r.text))
        return [m["id"] for m in r.json().get("data", []) if "id" in m]

    async def aclose(self) -> None:
        await self.client.aclose()
