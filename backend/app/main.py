"""Recast API — academic paraphrasing backend."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import model_config
from .config import get_settings
from .core.prompts import MODES, StyleOptions
from .model_config import ModelConfig
from .providers import LLMProvider, ProviderError, build_provider
from .schemas import (AlternativesRequest, AlternativesResponse, ModelConfigIn, ParaphraseRequest,
                      ParaphraseResponse, StyleFields)
from .services.paraphrase import Paraphraser

settings = get_settings()
state: dict = {}


def _activate(cfg: ModelConfig) -> None:
    """Make ``cfg`` the live model. Falls back to demo if it can't be built."""
    old: LLMProvider | None = state.get("provider")
    try:
        provider = build_provider(cfg)
        state["config_error"] = ""
    except ProviderError as e:
        provider = build_provider(ModelConfig(provider="demo"))
        state["config_error"] = str(e)
    state["config"] = cfg
    state["provider"] = provider
    state["engine"] = Paraphraser(provider, cfg.concurrency, settings.max_segment_words)
    if old is not None:
        # Requests already running still use the old client; close it later.
        asyncio.get_event_loop().call_later(900, lambda: asyncio.ensure_future(old.aclose()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _activate(model_config.load(settings))
    yield
    await state["provider"].aclose()


app = FastAPI(title="Recast API", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _opts(r: StyleFields) -> StyleOptions:
    return StyleOptions(r.mode, r.strength, r.dialect, r.voice, r.field, tuple(r.frozen_terms))


def _check_length(text: str) -> None:
    if len(text) > settings.max_input_chars:
        raise HTTPException(413, f"Text is longer than {settings.max_input_chars:,} characters. Split it into parts.")


# ------------------------------------------------------------------ status


@app.get("/api/health")
async def health() -> dict:
    p = state["provider"]
    return {"status": "ok", "provider": p.name, "model": p.model, "demo": p.is_demo,
            "max_input_chars": settings.max_input_chars, "config_error": state.get("config_error", "")}


@app.get("/api/modes")
async def modes() -> list[dict]:
    return [{"id": k, "label": v["label"], "description": v["description"]} for k, v in MODES.items()]


# --------------------------------------------------------------- rewriting


@app.post("/api/paraphrase", response_model=ParaphraseResponse)
async def paraphrase(req: ParaphraseRequest) -> dict:
    _check_length(req.text)
    try:
        return await state["engine"].run(req.text, req.format, _opts(req))
    except ProviderError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/paraphrase/stream")
async def paraphrase_stream(req: ParaphraseRequest) -> StreamingResponse:
    """Same as /api/paraphrase, but streams newline-delimited JSON progress events."""
    _check_length(req.text)
    engine: Paraphraser = state["engine"]

    async def events():
        async for ev in engine.stream(req.text, req.format, _opts(req)):
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/alternatives", response_model=AlternativesResponse)
async def alternatives(req: AlternativesRequest) -> dict:
    try:
        alts = await state["engine"].alternatives(req.sentence, req.context, _opts(req), req.count)
    except ProviderError as e:
        raise HTTPException(502, str(e)) from e
    return {"alternatives": alts}


# ------------------------------------------------------------- model setup


def _merge(body: ModelConfigIn) -> ModelConfig:
    current: ModelConfig = state["config"]
    data = body.model_dump()
    if data["api_key"] is None:
        # Reuse the saved key only for the same service, so a key is never
        # sent to a different provider by accident.
        same_service = current.provider == body.provider and current.base_url.rstrip("/") == body.base_url.rstrip("/")
        data["api_key"] = current.api_key if same_service else ""
    data["max_tokens"] = current.max_tokens
    return ModelConfig.model_validate(data)


@app.get("/api/settings/model")
async def get_model_settings() -> dict:
    return {**state["config"].public(), "error": state.get("config_error", "")}


@app.put("/api/settings/model")
async def put_model_settings(body: ModelConfigIn) -> dict:
    cfg = _merge(body)
    try:
        build_provider(cfg)  # validate before saving
    except ProviderError as e:
        raise HTTPException(400, str(e)) from e
    model_config.save(cfg)
    _activate(cfg)
    return {**cfg.public(), "error": ""}


@app.post("/api/settings/model/models")
async def list_models(body: ModelConfigIn) -> dict:
    try:
        provider = build_provider(_merge(body))
    except ProviderError as e:
        raise HTTPException(400, str(e)) from e
    try:
        return {"models": await provider.list_models()}
    except ProviderError as e:
        raise HTTPException(502, str(e)) from e
    finally:
        await provider.aclose()


@app.post("/api/settings/model/test")
async def test_model(body: ModelConfigIn) -> dict:
    """Send one real paraphrase request so the user knows the setup works."""
    cfg = _merge(body)
    try:
        provider = build_provider(cfg)
    except ProviderError as e:
        raise HTTPException(400, str(e)) from e
    engine = Paraphraser(provider, 1)
    sample = r"We uses the method of \cite{smith2020}, which reduce error by 12\% in our experiments."
    start = time.perf_counter()
    try:
        result = await engine.run(sample, "latex", StyleOptions(mode="fluency", strength=1))
    except ProviderError as e:
        raise HTTPException(502, str(e)) from e
    finally:
        await provider.aclose()
    seg = result["segments"][0]
    return {
        "ok": seg["status"] == "rewritten",
        "ms": int((time.perf_counter() - start) * 1000),
        "input": sample,
        "output": result["output"],
        "issues": seg["issues"],
    }
