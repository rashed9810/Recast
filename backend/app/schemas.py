from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Mode = Literal["academic", "standard", "fluency", "concise", "expand", "simplify"]


class StyleFields(BaseModel):
    mode: Mode = "academic"
    strength: int = Field(2, ge=1, le=3)
    dialect: Literal["en-US", "en-GB", "keep"] = "en-US"
    voice: Literal["keep", "active", "passive"] = "keep"
    field: str = Field("", max_length=80)
    frozen_terms: list[str] = Field(default_factory=list, max_length=60)

    @field_validator("frozen_terms")
    @classmethod
    def _clean_terms(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for t in v:
            t = t.strip()
            if t and t not in out and len(t) <= 80:
                out.append(t)
        return out


class ParaphraseRequest(StyleFields):
    text: str = Field(..., min_length=1)
    format: Literal["auto", "latex", "plain"] = "auto"


class IssueOut(BaseModel):
    level: Literal["error", "warning", "info"]
    code: str
    message: str


class SegmentOut(BaseModel):
    index: int
    number: int
    original: str
    output: str
    status: Literal["rewritten", "skipped", "fallback", "error"]
    similarity: float
    issues: list[IssueOut]


class DiffOp(BaseModel):
    op: Literal["equal", "insert", "delete"]
    text: str


class Metrics(BaseModel):
    words_in: int
    words_out: int
    similarity: float
    protected_spans: int
    segments_total: int
    segments_rewritten: int
    readability_in: float | None
    readability_out: float | None
    elapsed_ms: int
    detected_format: Literal["latex", "plain"]


class ParaphraseResponse(BaseModel):
    input: str
    output: str
    segments: list[SegmentOut]
    diff: list[DiffOp]
    metrics: Metrics
    provider: str
    model: str
    demo: bool


class AlternativesRequest(StyleFields):
    sentence: str = Field(..., min_length=1, max_length=2000)
    context: str = Field("", max_length=6000)
    count: int = Field(3, ge=1, le=5)


class AlternativesResponse(BaseModel):
    alternatives: list[str]


class ModelConfigIn(BaseModel):
    provider: Literal["openai", "anthropic", "demo"]
    preset: str = Field("custom", max_length=40)
    base_url: str = Field("", max_length=300)
    # None = keep the saved key; "" = remove it.
    api_key: str | None = Field(None, max_length=400)
    model: str = Field("", max_length=200)
    temperature: float = Field(0.4, ge=0.0, le=1.5)
    concurrency: int = Field(2, ge=1, le=8)
    timeout_seconds: float = Field(300.0, ge=10, le=1800)
