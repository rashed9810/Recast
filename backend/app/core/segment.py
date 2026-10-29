"""Split masked text into paragraph-sized segments the model handles well.

Masking happens on the *whole* document first, so an equation that contains
blank lines is already a single placeholder and can never be split in half.
Each segment keeps its own local placeholder numbering (⟦P0⟧, ⟦P1⟧ ...) so the
model sees small, tidy token ids.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .protect import PLACEHOLDER, PLACEHOLDER_RE, prose_only

PARA_SPLIT_RE = re.compile(r"(\n[ \t]*\n\s*)")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z⟦\\(\"'])")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


@dataclass
class Segment:
    index: int
    lead: str          # leading whitespace, re-attached unchanged
    body: str          # masked text with LOCAL placeholder ids
    trail: str         # trailing whitespace
    local_to_global: list[int] = field(default_factory=list)
    rewrite: bool = True  # False when there is no prose worth sending


def word_count(text: str) -> int:
    return len(WORD_RE.findall(prose_only(text)))


def _localise(body: str) -> tuple[str, list[int]]:
    mapping: list[int] = []
    seen: dict[int, int] = {}

    def repl(m: re.Match[str]) -> str:
        g = int(m.group(1))
        if g not in seen:
            seen[g] = len(mapping)
            mapping.append(g)
        return PLACEHOLDER.format(seen[g])

    return PLACEHOLDER_RE.sub(repl, body), mapping


def _split_long(chunk: str, max_words: int) -> list[str]:
    if word_count(chunk) <= max_words:
        return [chunk]
    sentences = SENTENCE_SPLIT_RE.split(chunk)
    pieces: list[str] = []
    current: list[str] = []
    count = 0
    for sent in sentences:
        w = word_count(sent)
        if current and count + w > max_words:
            pieces.append(" ".join(current))
            current, count = [], 0
        current.append(sent)
        count += w
    if current:
        pieces.append(" ".join(current))
    return pieces


def segment(masked_text: str, max_words: int = 380, min_words: int = 3) -> tuple[list[Segment], list[str]]:
    """Return segments plus the separators that sit between them.

    Rejoin with: seg0 + sep0 + seg1 + sep1 + ...
    Long paragraphs are split at sentence boundaries; the extra pieces are
    joined back with a single space.
    """
    parts = PARA_SPLIT_RE.split(masked_text)
    segments: list[Segment] = []
    separators: list[str] = []
    for k, part in enumerate(parts):
        if k % 2 == 1:
            separators.append(part)
            continue
        pieces = _split_long(part, max_words) if part.strip() else [part]
        for p_i, piece in enumerate(pieces):
            stripped = piece.strip()
            lead = piece[: len(piece) - len(piece.lstrip())]
            trail = piece[len(piece.rstrip()):] if stripped else ""
            body, mapping = _localise(stripped)
            segments.append(
                Segment(
                    index=len(segments),
                    lead=lead,
                    body=body,
                    trail=trail,
                    local_to_global=mapping,
                    rewrite=word_count(stripped) >= min_words,
                )
            )
            if p_i < len(pieces) - 1:
                separators.append(" ")
    return segments, separators


def globalise(local_text: str, mapping: list[int]) -> str:
    """Convert a segment's local placeholder ids back to document ids."""

    def repl(m: re.Match[str]) -> str:
        loc = int(m.group(1))
        return PLACEHOLDER.format(mapping[loc]) if 0 <= loc < len(mapping) else m.group(0)

    return PLACEHOLDER_RE.sub(repl, local_text)
