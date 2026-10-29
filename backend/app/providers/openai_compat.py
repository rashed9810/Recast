"""Any server that speaks the OpenAI Chat Completions API.

Works with Ollama (http://localhost:11434/v1), LM Studio
(http://localhost:1234/v1), vLLM, llama.cpp server, OpenAI, Groq, Google
Gemini's OpenAI-compatible endpoint, OpenRouter, Together, etc.
"""

from __future__ import annotations

import httpx

from .base import LLMProvider, ProviderError, friendly_http_error, is_retryable_status


class OpenAICompatProvider(LLMProvider):
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, temperature: float,
                 max_tokens: int, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        # Some newer models reject these parameters; we learn that from the
        # first error and stop sending them.
        self.send_temperature = True
        self.max_tokens_field = "max_tokens"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0), headers=headers
        )

    def _payload(self, system: str, user: str, temperature: float | None) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            self.max_tokens_field: self.max_tokens,
        }
        if self.send_temperature:
            payload["temperature"] = self.temperature if temperature is None else temperature
        return payload

    async def _complete(self, system: str, user: str, temperature: float | None) -> str:
        if not self.model:
            raise ProviderError("No model selected. Choose one in Model setup.")
        for _ in range(3):  # at most two parameter adjustments
            try:
                r = await self.client.post(f"{self.base_url}/chat/completions",
                                           json=self._payload(system, user, temperature))
            except httpx.TimeoutException as e:
                raise ProviderError(
                    "The model took too long to answer. A smaller model, or shorter paragraphs, will help.",
                    retryable=True) from e
            except httpx.HTTPError as e:
                raise ProviderError(
                    f"Could not reach the model server at {self.base_url}. Is it running? ({e.__class__.__name__})"
                ) from e
            if r.status_code == 400:
                text = r.text.lower()
                if "max_tokens" in text and self.max_tokens_field == "max_tokens":
                    self.max_tokens_field = "max_completion_tokens"
                    continue
                if "temperature" in text and self.send_temperature:
                    self.send_temperature = False
                    continue
            if r.status_code >= 400:
                raise ProviderError(friendly_http_error("The model server", r.status_code, r.text),
                                    retryable=is_retryable_status(r.status_code))
            try:
                msg = r.json()["choices"][0]["message"]
            except (KeyError, IndexError, ValueError) as e:
                raise ProviderError("Unexpected response format from the model server.") from e
            content = msg.get("content") or ""
            if isinstance(content, list):  # some servers return content parts
                content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
            return content
        raise ProviderError("The model server rejected the request parameters.")

    async def list_models(self) -> list[str]:
        try:
            r = await self.client.get(f"{self.base_url}/models")
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach {self.base_url}. Is the server running?") from e
        if r.status_code >= 400:
            raise ProviderError(friendly_http_error("The model server", r.status_code, r.text))
        try:
            data = r.json()
            items = data.get("data", data.get("models", [])) if isinstance(data, dict) else data
            ids = [m.get("id") or m.get("name") for m in items if isinstance(m, dict)]
        except (ValueError, AttributeError) as e:
            raise ProviderError("The server's model list was not in a format Recast understands.") from e
        # Gemini prefixes ids with "models/"; the chat endpoint accepts both.
        return sorted({i.removeprefix("models/") for i in ids if i})

    async def aclose(self) -> None:
        await self.client.aclose()
