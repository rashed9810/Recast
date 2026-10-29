"""Offline stand-in used when no model is configured, and in tests.

It does NOT paraphrase. It applies a handful of fixed word swaps so the whole
pipeline (masking, checks, diff, UI) can be exercised without any AI model.
"""

from __future__ import annotations

import json
import re

from .base import LLMProvider

SWAPS = [
    (r"\bIn order to\b", "To"), (r"\bin order to\b", "to"),
    (r"\buses\b", "employs"), (r"\buse\b", "employ"), (r"\bused\b", "employed"),
    (r"\bmethod\b", "approach"), (r"\bmethods\b", "approaches"),
    (r"\bHowever\b", "Nevertheless"), (r"\bbig\b", "large"),
    (r"\bimportant\b", "essential"), (r"\bhelps\b", "assists"),
    (r"\bshows\b", "indicates"), (r"\ba lot of\b", "many"),
]

PASSAGE_RE = re.compile(r"<<<\n(.*)\n>>>", re.S)


def _swap(text: str) -> str:
    for pat, rep in SWAPS:
        text = re.sub(pat, rep, text)
    return text


class DemoProvider(LLMProvider):
    name = "demo"
    model = "offline-demo"
    is_demo = True

    async def list_models(self) -> list[str]:
        return ["offline-demo"]

    async def _complete(self, system: str, user: str, temperature: float | None) -> str:
        m = PASSAGE_RE.search(user)
        passage = m.group(1) if m else user
        if "JSON array" in user:
            first = _swap(passage)
            return json.dumps([first, passage.replace(", ", "; ", 1)])
        return _swap(passage)
