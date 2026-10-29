"""Word-level diff between original and rewritten text."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

TOKEN_RE = re.compile(r"\S+\s*|\s+")


def word_diff(a: str, b: str) -> list[dict[str, str]]:
    """Return a list of {"op": equal|insert|delete, "text": ...} chunks."""
    ta, tb = TOKEN_RE.findall(a), TOKEN_RE.findall(b)
    # Compare on stripped tokens so whitespace differences don't add noise.
    ka, kb = [t.strip() for t in ta], [t.strip() for t in tb]
    ops: list[dict[str, str]] = []

    def push(op: str, text: str) -> None:
        if not text:
            return
        if ops and ops[-1]["op"] == op:
            ops[-1]["text"] += text
        else:
            ops.append({"op": op, "text": text})

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes():
        if tag == "equal":
            push("equal", "".join(tb[j1:j2]))
        else:
            push("delete", "".join(ta[i1:i2]))
            push("insert", "".join(tb[j1:j2]))
    return ops
