import os



from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, state  # noqa: E402
from app.providers.base import LLMProvider  # noqa: E402

SAMPLE = (r"In order to evaluate the method, we use the benchmark of \citet{doe2019}. "
          r"The loss $\mathcal{L}$ is defined in Eq.~\eqref{eq:1}." "\n\n"
          r"\begin{equation}a=b\label{eq:1}\end{equation}")


def test_health_and_modes():
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["demo"] is True
        ids = [m["id"] for m in c.get("/api/modes").json()]
        assert "academic" in ids and "fluency" in ids


def test_paraphrase_preserves_latex():
    with TestClient(app) as c:
        r = c.post("/api/paraphrase", json={"text": SAMPLE, "mode": "academic", "frozen_terms": ["benchmark"]})
        assert r.status_code == 200, r.text
        d = r.json()
        out = d["output"]
        for frag in [r"\citet{doe2019}", r"$\mathcal{L}$", r"\eqref{eq:1}", r"\begin{equation}a=b\label{eq:1}\end{equation}"]:
            assert frag in out
        assert out.startswith("To evaluate the approach, we employ")
        assert d["metrics"]["detected_format"] == "latex"
        assert d["segments"][1]["status"] == "skipped"


class DroppingProvider(LLMProvider):
    """Simulates a model that deletes protected tokens."""
    name, model = "bad", "bad"

    async def _complete(self, system, user, temperature=None):
        return "A sentence with all the tokens removed entirely."


def test_fallback_when_model_breaks_tokens():
    with TestClient(app) as c:
        engine = state["engine"]
        original = engine.provider
        engine.provider = DroppingProvider()
        try:
            d = c.post("/api/paraphrase", json={"text": SAMPLE}).json()
        finally:
            engine.provider = original
        assert d["output"] == SAMPLE
        assert d["segments"][0]["status"] == "fallback"
        assert d["segments"][0]["issues"][0]["code"] == "kept_original"


def test_alternatives_and_limits():
    with TestClient(app) as c:
        r = c.post("/api/alternatives", json={"sentence": r"We use the method of \cite{a}, which helps a lot."})
        alts = r.json()["alternatives"]
        assert alts and all(r"\cite{a}" in a for a in alts)
        assert c.post("/api/paraphrase", json={"text": "x" * 70_000}).status_code == 413
        assert c.post("/api/paraphrase", json={"text": "hi", "strength": 9}).status_code == 422
