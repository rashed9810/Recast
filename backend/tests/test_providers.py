import asyncio
import json

import httpx
import pytest

from app.providers.anthropic import AnthropicProvider
from app.providers.base import ProviderError
from app.providers.openai_compat import OpenAICompatProvider


def run(coro):
    return asyncio.run(coro)


def test_openai_compatible_request_and_parse():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "rewritten"}}]})

    p = OpenAICompatProvider("http://localhost:11434/v1/", "key", "m", 0.3, 100, 10)
    p.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=p.client.headers)
    assert run(p.complete("sys", "user")) == "rewritten"
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["auth"] == "Bearer key"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}


def test_openai_error_is_readable():
    p = OpenAICompatProvider("http://x/v1", "", "m", 0.3, 100, 10)
    p.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="bad key")))
    with pytest.raises(ProviderError, match="401"):
        run(p.complete("s", "u"))


def test_anthropic_request_and_parse():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["headers"] = req.headers
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    p = AnthropicProvider("k", "claude-x", 0.3, 100, 10)
    p.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=p.client.headers)
    assert run(p.complete("sys", "user")) == "ok"
    assert seen["headers"]["x-api-key"] == "k"
    assert seen["body"]["system"] == "sys" and seen["body"]["model"] == "claude-x"


def test_anthropic_requires_key():
    with pytest.raises(ProviderError):
        AnthropicProvider("", "m", 0.3, 100, 10)


def test_openai_adapts_to_newer_model_parameters():
    bodies = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        bodies.append(body)
        if "max_tokens" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens'."}})
        if "temperature" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature' does not support 0.4"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "fine"}}]})

    p = OpenAICompatProvider("http://x/v1", "k", "m", 0.4, 100, 10)
    p.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert run(p.complete("s", "u")) == "fine"
    assert "max_completion_tokens" in bodies[-1] and "temperature" not in bodies[-1]
    assert run(p.complete("s", "u")) == "fine" and len(bodies) == 4  # remembered


def test_list_models_handles_gemini_prefix():
    p = OpenAICompatProvider("http://x/v1", "k", "m", 0.4, 100, 10)
    p.client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"data": [{"id": "models/gemini-x"}, {"id": "llama"}]})))
    assert run(p.list_models()) == ["gemini-x", "llama"]
