from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod


class ProviderError(RuntimeError):
    """Raised when the model backend fails or returns something unusable.

    ``retryable`` marks temporary problems (rate limits, overload, timeouts)
    that are worth trying again after a short wait.
    """

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def is_retryable_status(code: int) -> bool:
    return code in {408, 409, 425, 429} or code >= 500


def friendly_http_error(service: str, code: int, body: str) -> str:
    hint = {
        401: "The API key was rejected. Check it in Model setup.",
        403: "Access denied. The key may not have permission for this model.",
        404: "Not found. Check the server address and the model name.",
        429: "Rate limit reached. Wait a moment, or lower 'parallel requests' in Model setup.",
    }.get(code, "")
    detail = body.strip().replace("\n", " ")[:240]
    return f"{service} returned {code}. {hint} {detail}".strip()


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""
    is_demo: bool = False

    async def complete(self, system: str, user: str, temperature: float | None = None) -> str:
        """Return the model's reply, retrying temporary failures."""
        delay = 2.0
        for attempt in range(3):
            try:
                return await self._complete(system, user, temperature)
            except ProviderError as e:
                if not e.retryable or attempt == 2:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")

    @abstractmethod
    async def _complete(self, system: str, user: str, temperature: float | None) -> str:
        """One request to the model."""

    async def list_models(self) -> list[str]:
        return [self.model] if self.model else []

    async def aclose(self) -> None:  # pragma: no cover - optional hook
        return None
