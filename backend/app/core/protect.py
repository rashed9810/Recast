"""Protect fragile content (LaTeX, math, citations, URLs) from the language model.

The idea is simple: before text goes to the model, every span that must not
change is cut out and replaced by a short token such as ``⟦P3⟧``. The model
only ever sees prose plus tokens. Afterwards the tokens are swapped back for
the original spans, byte for byte.

The scanner is a small hand-written parser rather than a pile of regexes,
because LaTeX braces nest and regexes cannot match nested braces reliably.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PLACEHOLDER = "⟦P{}⟧"
# Models, especially small local ones, often rewrite the brackets: ⟦P0⟧ may
# come back as [[P0]], [P0], 【P0】 or ⟨P0⟩. All of these are accepted.
PLACEHOLDER_RE = re.compile(
    r"(?:⟦|〚|\[\[|【|\[|⟨|<<|\{\{)\s*P\s*(\d+)\s*(?:⟧|〛|\]\]|】|\]|⟩|>>|\}\})"
)

# Environments copied verbatim as one block (content is never rewritten).
BLOCK_ENVS = {
    "equation", "equation*", "align", "align*", "alignat", "alignat*",
    "gather", "gather*", "multline", "multline*", "flalign", "flalign*",
    "eqnarray", "eqnarray*", "displaymath", "math", "split", "cases",
    "figure", "figure*", "table", "table*", "tabular", "tabular*", "tabularx",
    "longtable", "algorithm", "algorithmic", "algorithm2e", "tikzpicture",
    "lstlisting", "minted", "verbatim", "Verbatim", "comment",
    "thebibliography", "bmatrix", "pmatrix", "matrix",
}

# Commands whose argument is prose that *should* be rewritten. Only the
# opening ``\cmd{`` and closing ``}`` are protected; the inside is scanned.
TEXT_ARG_COMMANDS = {"footnote", "caption", "textsc"}

URL_RE = re.compile(r"(?:https?://|www\.)[^\s{}<>]+|\bdoi:\s*\S+|\b10\.\d{4,9}/[^\s{}]+")
NUMERIC_CITE_RE = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]")
LATEX_HINT_RE = re.compile(r"\\[A-Za-z]+|\$[^$\n]+\$|\\\(|\\\[")


@dataclass
class Masked:
    """Text with protected spans replaced by placeholders."""

    text: str
    spans: list[str] = field(default_factory=list)
    # (open_id, close_id) pairs that must stay in order, e.g. \footnote{ ... }
    pairs: list[tuple[int, int]] = field(default_factory=list)


def looks_like_latex(text: str) -> bool:
    return bool(LATEX_HINT_RE.search(text))


def _strip_url_tail(url: str) -> str:
    while url and url[-1] in ".,;:)]'\"":
        url = url[:-1]
    return url


def _match_group(s: str, i: int, open_c: str, close_c: str) -> int:
    """Given s[i] == open_c, return the index just after its matching close.

    Returns -1 when unbalanced.
    """
    depth = 0
    j = i
    n = len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return -1


def _find_unescaped(s: str, i: int, target: str) -> int:
    """Index of the next unescaped ``target`` at or after i, else -1."""
    j = i
    n = len(s)
    while j < n:
        if s.startswith(target, j):
            return j
        if s[j] == "\\":
            j += 2
            continue
        j += 1
    return -1


def _find_env_end(s: str, i: int, name: str) -> int:
    """Index just after the ``\\end{name}`` matching the ``\\begin{name}`` at i."""
    begin, end = f"\\begin{{{name}}}", f"\\end{{{name}}}"
    depth = 0
    j = i
    while j < len(s):
        if s.startswith(begin, j):
            depth += 1
            j += len(begin)
        elif s.startswith(end, j):
            depth -= 1
            j += len(end)
            if depth == 0:
                return j
        else:
            j += 1
    return -1


def _consume_args(s: str, j: int) -> int:
    """Skip any directly-following [optional] and {required} argument groups."""
    while j < len(s) and s[j] in "[{":
        close = "]" if s[j] == "[" else "}"
        k = _match_group(s, j, s[j], close)
        if k == -1:
            break
        j = k
    return j


class _Builder:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.spans: list[str] = []
        self.pairs: list[tuple[int, int]] = []
        self._last_was_span = False

    def text(self, t: str) -> None:
        if t:
            self.parts.append(t)
            self._last_was_span = False

    def protect(self, raw: str, mergeable: bool = True) -> int:
        """Store a span and emit its placeholder. Adjacent spans are merged."""
        if mergeable and self._last_was_span and self.spans:
            self.spans[-1] += raw
            return len(self.spans) - 1
        self.spans.append(raw)
        idx = len(self.spans) - 1
        self.parts.append(PLACEHOLDER.format(idx))
        self._last_was_span = mergeable
        return idx

    def result(self) -> Masked:
        return Masked("".join(self.parts), self.spans, self.pairs)


def mask_plain(text: str) -> Masked:
    """Protect only URLs, DOIs and numeric citations like [12] or [3-5]."""
    b = _Builder()
    pattern = re.compile(f"{PLACEHOLDER_RE.pattern}|{URL_RE.pattern}|{NUMERIC_CITE_RE.pattern}")
    pos = 0
    for m in pattern.finditer(text):
        raw = m.group(0)
        if raw[0] not in "[⟦〚【⟨<{":
            raw = _strip_url_tail(raw)
        b.text(text[pos:m.start()])
        b.protect(raw, mergeable=False)
        pos = m.start() + len(raw)
    b.text(text[pos:])
    return b.result()


def mask_latex(s: str) -> Masked:
    """Protect LaTeX markup, math, comments, citations and URLs."""
    b = _Builder()
    buf: list[str] = []
    open_stack: list[int] = []  # placeholder ids of open \footnote{ etc.
    i, n = 0, len(s)

    def flush() -> None:
        if buf:
            b.text("".join(buf))
            buf.clear()

    def protect(raw: str, mergeable: bool = True) -> int:
        flush()
        return b.protect(raw, mergeable)

    while i < n:
        c = s[i]

        # Text that already looks like one of our tokens (e.g. "[P1]" for a
        # study participant) is protected so it can never be confused.
        if c in "[⟦〚【⟨<{":
            m = PLACEHOLDER_RE.match(s, i)
            if m:
                protect(m.group(0))
                i = m.end()
                continue

        # Comment: % up to (not including) the newline.
        if c == "%":
            j = s.find("\n", i)
            j = n if j == -1 else j
            protect(s[i:j])
            i = j
            continue

        # Environments.
        if s.startswith("\\begin{", i):
            k = s.find("}", i)
            name = s[i + 7:k] if k != -1 else ""
            if name in BLOCK_ENVS:
                j = _find_env_end(s, i, name)
                if j != -1:
                    protect(s[i:j])
                    i = j
                    continue
            j = _consume_args(s, k + 1) if k != -1 else i + 7
            protect(s[i:j])
            i = j
            continue
        if s.startswith("\\end{", i):
            k = s.find("}", i)
            j = k + 1 if k != -1 else i + 5
            protect(s[i:j])
            i = j
            continue

        # Display and inline math.
        handled = False
        for opener, closer in (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)")):
            if s.startswith(opener, i):
                j = _find_unescaped(s, i + len(opener), closer)
                if j != -1:
                    protect(s[i:j + len(closer)])
                    i = j + len(closer)
                else:  # unmatched opener: protect it literally
                    protect(opener)
                    i += len(opener)
                handled = True
                break
        if handled:
            continue

        if c == "$":
            j = _find_unescaped(s, i + 1, "$")
            if j != -1:
                protect(s[i:j + 1])
                i = j + 1
            else:
                protect("$")
                i += 1
            continue

        # Commands.
        if c == "\\":
            if i + 1 < n and s[i + 1].isalpha():
                j = i + 1
                while j < n and s[j].isalpha():
                    j += 1
                if j < n and s[j] == "*":
                    j += 1
                name = s[i + 1:j].rstrip("*")
                # optional [args] for text-argument commands, then '{'
                k = j
                while k < n and s[k] == "[":
                    m = _match_group(s, k, "[", "]")
                    if m == -1:
                        break
                    k = m
                if name in TEXT_ARG_COMMANDS and k < n and s[k] == "{":
                    idx = protect(s[i:k + 1], mergeable=False)
                    open_stack.append(idx)
                    i = k + 1
                    continue
                j = _consume_args(s, j)
                protect(s[i:j])
                i = j
            else:  # control symbol: \% \& \\ \, \_ etc.
                protect(s[i:i + 2])
                i += 2
            continue

        # Bare brace group, e.g. {GPU}s
        if c == "{":
            j = _match_group(s, i, "{", "}")
            if j != -1:
                protect(s[i:j])
                i = j
            else:
                protect("{")
                i += 1
            continue

        if c == "}":
            idx = protect("}", mergeable=False)
            if open_stack:
                b.pairs.append((open_stack.pop(), idx))
            i += 1
            continue

        # Non-breaking space ties (Eq.~\ref) travel with the next protected item.
        if c == "~":
            protect("~")
            i += 1
            continue

        # URLs
        if c in "hwd1":
            m = URL_RE.match(s, i)
            if m and (i == 0 or not s[i - 1].isalnum()):
                raw = _strip_url_tail(m.group(0))
                protect(raw)
                i += len(raw)
                continue

        buf.append(c)
        i += 1

    flush()
    return b.result()


def mask(text: str, fmt: str = "auto") -> Masked:
    """Mask ``text``. ``fmt`` is 'latex', 'plain' or 'auto'."""
    if fmt == "auto":
        fmt = "latex" if looks_like_latex(text) else "plain"
    return mask_latex(text) if fmt == "latex" else mask_plain(text)


def placeholder_ids(text: str) -> list[int]:
    return [int(m.group(1)) for m in PLACEHOLDER_RE.finditer(text)]


def unmask(text: str, spans: list[str]) -> str:
    """Replace every placeholder with its original span."""

    def repl(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        return spans[idx] if 0 <= idx < len(spans) else m.group(0)

    return PLACEHOLDER_RE.sub(repl, text)


def prose_only(text: str) -> str:
    """Masked text with placeholders removed: the part the model may rewrite."""
    return PLACEHOLDER_RE.sub(" ", text)


_HYPHEN_BREAK_RE = re.compile(r"(?<=[a-z])-\n(?=[a-z])")
_LIST_START_RE = re.compile(r"^\s*(?:[-•*–]\s|\(?\d+[.)]\s|\(?[a-z][.)]\s)")


def normalise_plain(text: str) -> str:
    """Undo PDF copy-paste artefacts in plain text.

    * ``seg-\nmentation`` becomes ``segmentation`` (``state-of-\nthe-art``
      keeps its hyphen because the left part is already hyphenated).
    * Single line breaks inside a paragraph become spaces, except before list
      items. Blank lines (paragraph breaks) are kept.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    def dehyphen(m: re.Match[str]) -> str:
        start = m.start()
        word_start = max(text.rfind(" ", 0, start), text.rfind("\n", 0, start)) + 1
        return "-" if "-" in text[word_start:start] else ""

    text = _HYPHEN_BREAK_RE.sub(dehyphen, text)
    paragraphs = re.split(r"(\n[ \t]*\n\s*)", text)
    out: list[str] = []
    for k, para in enumerate(paragraphs):
        if k % 2 == 1:
            out.append(para)
            continue
        lines = para.split("\n")
        joined = lines[0]
        for line in lines[1:]:
            if _LIST_START_RE.match(line) or not line.strip():
                joined += "\n" + line
            else:
                joined = joined.rstrip() + " " + line.lstrip()
        out.append(joined)
    return "".join(out)
