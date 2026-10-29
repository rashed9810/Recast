"""Automatic checks that flag possible meaning changes.

These are heuristics, not proof. A clean report means nothing obvious went
wrong; it does not replace the author reading the result.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

from .protect import placeholder_ids, prose_only

NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])[-+−]?\d+(?:[.,]\d+)*(?:\s?%)?")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")

NEGATIONS = {"not", "no", "never", "neither", "nor", "without", "cannot", "none", "nothing", "nobody", "fail", "fails", "failed", "lack", "lacks"}
HEDGES = {"may", "might", "could", "possibly", "potentially", "suggest", "suggests", "suggested", "appear", "appears",
          "likely", "unlikely", "perhaps", "indicate", "indicates", "seem", "seems", "plausibly", "presumably", "tend", "tends"}
STRONG = {"prove", "proves", "proved", "proven", "always", "never", "certainly", "definitely", "undoubtedly",
          "guarantee", "guarantees", "conclusively", "clearly", "unquestionably", "establish", "establishes"}


@dataclass
class Issue:
    level: str   # "error" | "warning" | "info"
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"level": self.level, "code": self.code, "message": self.message}


def check_placeholders(output: str, expected: int, pairs: list[tuple[int, int]] | None = None) -> list[Issue]:
    ids = placeholder_ids(output)
    counts = Counter(ids)
    issues: list[Issue] = []
    missing = sorted(set(range(expected)) - set(ids))
    invented = sorted(i for i in counts if i >= expected)
    dupes = sorted(i for i, c in counts.items() if c > 1 and i < expected)
    if missing:
        issues.append(Issue("error", "placeholder_missing", f"Protected items dropped: {missing}"))
    if invented:
        issues.append(Issue("error", "placeholder_invented", f"Unknown protected items added: {invented}"))
    if dupes:
        issues.append(Issue("error", "placeholder_duplicated", f"Protected items repeated: {dupes}"))
    if not issues and pairs:
        pos = {i: k for k, i in enumerate(ids)}
        for a, b in pairs:
            if a in pos and b in pos and pos[a] > pos[b]:
                issues.append(Issue("error", "placeholder_order", "A footnote or caption was broken apart."))
                break
    return issues


def _normalise_number(n: str) -> str:
    return n.replace("−", "-").replace(" ", "").lstrip("+")


def extract_numbers(text: str) -> Counter[str]:
    return Counter(_normalise_number(m) for m in NUMBER_RE.findall(prose_only(text)))


def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(prose_only(text))]


def similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa and not wb:
        return 1.0
    return round(SequenceMatcher(None, wa, wb, autojunk=False).ratio(), 3)


def check_meaning(original: str, output: str, mode: str, frozen_terms: tuple[str, ...] = ()) -> list[Issue]:
    """Heuristic checks run on masked text (protected spans are already safe)."""
    issues: list[Issue] = []

    n_in, n_out = extract_numbers(original), extract_numbers(output)
    lost = sorted((n_in - n_out).elements())
    added = sorted((n_out - n_in).elements())
    if lost:
        issues.append(Issue("warning", "numbers_changed", f"Numbers missing from the rewrite: {', '.join(lost)}"))
    if added:
        issues.append(Issue("warning", "numbers_added", f"New numbers appeared: {', '.join(added)}"))

    for term in frozen_terms:
        if term and term.lower() in original.lower() and term not in output:
            issues.append(Issue("warning", "term_changed", f'Locked term "{term}" was altered or removed.'))

    w_in, w_out = _words(original), _words(output)
    c_in, c_out = Counter(w_in), Counter(w_out)
    neg_in = sum(c_in[w] for w in NEGATIONS) + sum(w.endswith("n't") for w in w_in)
    neg_out = sum(c_out[w] for w in NEGATIONS) + sum(w.endswith("n't") for w in w_out)
    if neg_in != neg_out:
        issues.append(Issue("warning", "negation_changed",
                            "The number of negations changed. Check that no statement was reversed."))

    hedge_in = sum(c_in[w] for w in HEDGES)
    hedge_out = sum(c_out[w] for w in HEDGES)
    if hedge_in and hedge_out < hedge_in:
        issues.append(Issue("warning", "hedging_reduced",
                            "Hedging words were removed. A tentative claim may now sound definite."))
    new_strong = sorted({w for w in c_out if w in STRONG and c_out[w] > c_in[w]})
    if new_strong:
        issues.append(Issue("warning", "certainty_increased",
                            f"Stronger certainty words introduced: {', '.join(new_strong)}."))

    if w_in:
        ratio = len(w_out) / len(w_in)
        limits = {"concise": (0.45, 1.05), "expand": (0.9, 1.9), "fluency": (0.8, 1.25)}.get(mode, (0.6, 1.5))
        if ratio < limits[0]:
            issues.append(Issue("warning", "too_short", f"Rewrite is {ratio:.0%} of the original length; content may be lost."))
        elif ratio > limits[1]:
            issues.append(Issue("warning", "too_long", f"Rewrite is {ratio:.0%} of the original length; content may have been added."))

    sim = similarity(original, output)
    if sim >= 0.97 and mode != "fluency" and len(w_in) >= 8:
        issues.append(Issue("info", "unchanged",
                            "The model returned this paragraph almost unchanged. Try the Strong setting or a larger model."))
    if sim < 0.25 and mode not in {"simplify"}:
        issues.append(Issue("info", "large_rewrite", "Heavily reworded. Read this paragraph carefully against the original."))
    return issues


def _syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and count > 1 and not word.endswith("le"):
        count -= 1
    return max(1, count)


def flesch_reading_ease(text: str) -> float | None:
    words = WORD_RE.findall(prose_only(text))
    sentences = max(1, len(re.findall(r"[.!?](?:\s|$)", text)))
    if len(words) < 5:
        return None
    syl = sum(_syllables(w) for w in words)
    score = 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syl / len(words))
    return round(score, 1)
