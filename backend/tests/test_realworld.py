"""Regression tests for failures seen with real models and real documents."""

import json
import re

from fastapi.testclient import TestClient

from app.core.protect import mask, normalise_plain, unmask
from app.main import app, state
from app.providers.base import LLMProvider, ProviderError
from app.services.paraphrase import clean_model_output

PASSAGE_RE = re.compile(r"<<<\n(.*)\n>>>", re.S)


class ScriptedProvider(LLMProvider):
    """Echoes the passage through a transform, like a (badly behaved) model."""

    name, model = "scripted", "scripted"

    def __init__(self, transform):
        self.transform = transform
        self.calls = 0

    async def _complete(self, system, user, temperature=None):
        self.calls += 1
        m = PASSAGE_RE.search(user)
        return self.transform(m.group(1) if m else user, self.calls)


def run_with(provider, payload, path="/api/paraphrase"):
    with TestClient(app) as c:
        engine = state["engine"]
        original = engine.provider
        engine.provider = provider
        try:
            return c.post(path, json=payload)
        finally:
            engine.provider = original


TEXT = r"Our method uses a important block~\cite{a} that improves Dice by 2.1\% in $N=5$ runs."


# ------------------------------------------------------------ cleaning


def test_thinking_and_preamble_are_removed():
    raw = "<think>\nLet me keep the tokens.\n</think>\n\nSure! Here is the rewritten passage:\n\nThe text ⟦P0⟧."
    assert clean_model_output(raw, "Text ⟦P0⟧.") == "The text ⟦P0⟧."
    assert clean_model_output("Okay, let me think.</think>The text.", "Text.") == "The text."
    assert clean_model_output("**Rewritten passage:** The text.", "Text.") == "The text."


def test_trailing_notes_are_removed_but_real_text_kept():
    assert clean_model_output("The text.\n\nNote: I kept all tokens.", "Text.") == "The text."
    assert clean_model_output("The text.\nChanges made: fixed grammar.", "Text.") == "The text."
    # A passage that really contains "Note" mid-text is untouched.
    assert clean_model_output("Note that the loss converges.", "Note that loss converges.") == "Note that the loss converges."


def test_end_to_end_messy_model_output_is_clean():
    def messy(p, _):
        return "<think>plan</think>Here is the rewritten passage:\n\n" + p.replace("uses a important", "employs an essential") + "\n\nNote: tokens preserved."

    d = run_with(ScriptedProvider(messy), {"text": TEXT}).json()
    assert d["output"] == r"Our method employs an essential block~\cite{a} that improves Dice by 2.1\% in $N=5$ runs."
    assert d["segments"][0]["status"] == "rewritten"


# ----------------------------------------------------- token tolerance


def test_ascii_brackets_from_small_models_are_accepted():
    def ascii_tokens(p, _):
        return re.sub(r"⟦P(\d+)⟧", r"[[P\1]]", p.replace("uses", "employs"))

    d = run_with(ScriptedProvider(ascii_tokens), {"text": TEXT}).json()
    assert d["segments"][0]["status"] == "rewritten"
    assert r"\cite{a}" in d["output"] and "[[P" not in d["output"]


def test_user_text_that_looks_like_a_token_is_safe():
    text = "Participant [P1] said the tool helped, while [P2] disagreed."
    m = mask(text, "plain")
    assert unmask(m.text, m.spans) == text
    d = run_with(ScriptedProvider(lambda p, _: p.replace("helped", "assisted")), {"text": text}).json()
    assert d["output"] == "Participant [P1] said the tool assisted, while [P2] disagreed."


def test_retry_then_success_on_second_attempt():
    d = run_with(ScriptedProvider(lambda p, n: "Lost all tokens here." if n == 1 else p), {"text": TEXT}).json()
    seg = d["segments"][0]
    assert seg["status"] == "rewritten" and seg["issues"][0]["code"] == "retried"


# ------------------------------------------------------- PDF artefacts


def test_pdf_line_breaks_and_hyphenation():
    raw = "Medical image seg-\nmentation is a\nstate-of-\nthe-art task.\n\nSecond para-\ngraph here:\n- first item\n- second item"
    assert normalise_plain(raw) == (
        "Medical image segmentation is a state-of-the-art task.\n\nSecond paragraph here:\n- first item\n- second item"
    )


# ----------------------------------------------------- model failures


class FailingProvider(LLMProvider):
    name, model = "down", "down"

    async def _complete(self, system, user, temperature=None):
        raise ProviderError("Could not reach the model server. Is it running?")


def test_all_paragraphs_failing_gives_clear_error():
    r = run_with(FailingProvider(), {"text": TEXT})
    assert r.status_code == 502 and "Is it running" in r.json()["detail"]


def test_one_failing_paragraph_keeps_the_rest():
    def flaky(p, n):
        if "Second" in p:
            raise ProviderError("Rate limit reached.")
        return p.replace("uses", "employs")

    d = run_with(ScriptedProvider(flaky), {"text": TEXT + "\n\nSecond paragraph uses words here."}).json()
    statuses = [s["status"] for s in d["segments"]]
    assert statuses == ["rewritten", "error"]
    assert "Second paragraph uses words here." in d["output"]


def test_transient_errors_are_retried(monkeypatch):
    import app.providers.base as base

    async def no_sleep(_):
        return None

    monkeypatch.setattr(base.asyncio, "sleep", no_sleep)

    class Flaky(LLMProvider):
        name, model = "flaky", "flaky"
        n = 0

        async def _complete(self, system, user, temperature=None):
            self.n += 1
            if self.n < 3:
                raise ProviderError("overloaded", retryable=True)
            return PASSAGE_RE.search(user).group(1)

    d = run_with(Flaky(), {"text": TEXT}).json()
    assert d["segments"][0]["status"] == "rewritten"


# ---------------------------------------------------------- streaming


def test_stream_reports_progress_then_result():
    r = run_with(ScriptedProvider(lambda p, _: p), {"text": TEXT + "\n\nAnother paragraph of real prose."},
                 "/api/paraphrase/stream")
    events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert types[0] == "start" and events[0]["total"] == 2
    assert types.count("progress") == 2 and types[-1] == "result"
    assert events[-1]["data"]["output"].startswith("Our method")


def test_stream_error_event():
    r = run_with(FailingProvider(), {"text": TEXT}, "/api/paraphrase/stream")
    last = json.loads(r.text.strip().splitlines()[-1])
    assert last["type"] == "error" and "Is it running" in last["message"]


# --------------------------------------------------------- model setup


def test_model_settings_never_expose_or_leak_key():
    with TestClient(app) as c:
        put = c.put("/api/settings/model", json={
            "provider": "openai", "preset": "groq", "base_url": "https://api.groq.com/openai/v1",
            "api_key": "gsk_secret_key_1234", "model": "some-model"})
        assert put.status_code == 200
        got = c.get("/api/settings/model").json()
        assert "api_key" not in got and got["has_key"] and got["key_hint"] == "…1234"
        assert "secret" not in json.dumps(got)
        # Same service, key omitted -> saved key kept.
        c.put("/api/settings/model", json={"provider": "openai", "preset": "groq",
                                           "base_url": "https://api.groq.com/openai/v1", "model": "other"})
        assert state["config"].api_key == "gsk_secret_key_1234"
        # Different service, key omitted -> key NOT carried over.
        c.put("/api/settings/model", json={"provider": "openai", "preset": "ollama",
                                           "base_url": "http://localhost:11434/v1", "model": "m"})
        assert state["config"].api_key == ""
        assert c.get("/api/health").json()["demo"] is False
        # Back to demo for the other tests.
        c.put("/api/settings/model", json={"provider": "demo", "preset": "demo"})
        assert c.get("/api/health").json()["demo"] is True


def test_model_test_endpoint_with_demo():
    with TestClient(app) as c:
        d = c.post("/api/settings/model/test", json={"provider": "demo"}).json()
        assert d["ok"] is True and r"\cite{smith2020}" in d["output"]
        assert c.post("/api/settings/model/models", json={"provider": "demo"}).json()["models"] == ["offline-demo"]


def test_invalid_settings_are_rejected():
    with TestClient(app) as c:
        r = c.put("/api/settings/model", json={"provider": "anthropic", "base_url": "", "api_key": ""})
        assert r.status_code == 400 and "API key" in r.json()["detail"]
