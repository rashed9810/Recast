"""The paraphrasing pipeline: mask → segment → rewrite → verify → restore."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from ..core import protect
from ..core.diff import word_diff
from ..core.prompts import SYSTEM_PROMPT, StyleOptions, alternatives_prompt, paraphrase_prompt
from ..core.segment import Segment, globalise, segment, word_count
from ..core.validate import Issue, check_meaning, check_placeholders, flesch_reading_ease, similarity
from ..providers import LLMProvider, ProviderError

# ---------------------------------------------------------------- cleaning

THINK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)
SPECIAL_TOKEN_RE = re.compile(r"<\|[^|>]{1,40}\|>")
FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*\n?|\n?```\s*$")
PREAMBLE_RE = re.compile(
    r"^\s*(?:\*\*)?(?:here(?:'s| is| are)|sure|certainly|of course|okay|ok|below is|the following is|"
    r"rewritten|revised|paraphrased|improved|edited|output|result|answer)\b[^\n]{0,120}?:(?:\*\*)?[ \t]*(?:\n+|(?=\S))",
    re.I,
)
NOTE_RE = re.compile(
    r"\n\s*(?:\*\*)?(?:note|notes|explanation|changes(?: made)?|summary of changes|i (?:have|'ve) |this (?:revision|version|rewrite))"
    r"\b[\s\S]*$",
    re.I,
)
QUOTES = {('"', '"'), ("“", "”"), ("'", "'"), ("«", "»")}


def clean_model_output(text: str, original: str = "") -> str:
    """Strip the wrapping that models add despite instructions.

    ``original`` is the masked input; it is used so that, e.g., a passage that
    really does start with "Note:" is not damaged.
    """
    t = text.replace("\r\n", "\n")
    if "</think>" in t:  # some servers drop the opening tag
        t = t.rsplit("</think>", 1)[1]
    t = THINK_RE.sub("", t)
    t = SPECIAL_TOKEN_RE.sub("", t).strip()
    t = FENCE_RE.sub("", t).strip()
    for _ in range(2):  # "Sure! Here is the rewritten passage:" can be two layers
        m = PREAMBLE_RE.match(t)
        if m and not PREAMBLE_RE.match(original) and len(t) > m.end():
            t = t[m.end():].strip()
    t = t.removeprefix("<<<").removesuffix(">>>").strip()
    m = NOTE_RE.search("\n" + t)
    if m and m.start() > 0 and not NOTE_RE.search("\n" + original):
        t = ("\n" + t)[: m.start()].strip()
    if len(t) > 1 and (t[0], t[-1]) in QUOTES and not ((original[:1], original[-1:]) in QUOTES):
        t = t[1:-1].strip()
    # One paragraph in, one paragraph out (but single line breaks are kept).
    return re.sub(r"\n[ \t]*\n\s*", " ", t).strip()


# ---------------------------------------------------------------- pipeline


@dataclass
class SegmentResult:
    seg: Segment
    output_local: str
    status: str  # rewritten | skipped | fallback | error
    issues: list[Issue] = field(default_factory=list)
    error: str = ""


@dataclass
class Job:
    text: str
    detected: str
    masked: protect.Masked
    segments: list[Segment]
    separators: list[str]
    started: float


class Paraphraser:
    def __init__(self, provider: LLMProvider, concurrency: int = 2, max_segment_words: int = 300) -> None:
        self.provider = provider
        self.sem = asyncio.Semaphore(max(1, concurrency))
        self.max_segment_words = max_segment_words

    # -- one paragraph

    async def _rewrite_segment(self, seg: Segment, opts: StyleOptions, pairs_local: list[tuple[int, int]]) -> SegmentResult:
        if not seg.rewrite:
            return SegmentResult(seg, seg.body, "skipped")
        expected = len(seg.local_to_global)
        retry_note = ""
        last_issues: list[Issue] = []
        try:
            for attempt in range(2):
                async with self.sem:
                    raw = await self.provider.complete(
                        SYSTEM_PROMPT,
                        paraphrase_prompt(seg.body, opts, retry_note, expected),
                        temperature=None if attempt == 0 else 0.2,
                    )
                out = clean_model_output(raw, seg.body)
                if not out:
                    last_issues = [Issue("error", "empty_output", "The model returned nothing.")]
                    retry_note = "Your previous answer was empty. Return the rewritten passage."
                    continue
                last_issues = check_placeholders(out, expected, pairs_local)
                if not last_issues:
                    issues = check_meaning(seg.body, out, opts.mode, opts.frozen_terms)
                    if attempt:
                        issues.insert(0, Issue("info", "retried", "Needed a second attempt to keep protected items intact."))
                    return SegmentResult(seg, out, "rewritten", issues)
                tokens = " ".join(protect.PLACEHOLDER.format(i) for i in range(expected)) or "(none)"
                retry_note = ("Your previous answer did not keep the protected tokens intact. The output must contain "
                              f"each of these tokens exactly once, unchanged: {tokens}.")
        except ProviderError as e:
            return SegmentResult(seg, seg.body, "error",
                                 [Issue("error", "model_error", f"Kept the original paragraph. {e}")], error=str(e))
        fallback = [Issue("error", "kept_original",
                          "Kept the original paragraph because the model could not preserve the protected LaTeX, "
                          "citations or equations. Try again, or use a larger model.")]
        return SegmentResult(seg, seg.body, "fallback", fallback + last_issues)

    # -- whole document

    def _prepare(self, text: str, fmt: str) -> Job:
        detected = "latex" if (fmt == "latex" or (fmt == "auto" and protect.looks_like_latex(text))) else "plain"
        if detected == "plain":
            text = protect.normalise_plain(text)
        masked = protect.mask(text, detected)
        segments, separators = segment(masked.text, self.max_segment_words)
        return Job(text, detected, masked, segments, separators, time.perf_counter())

    def _tasks(self, job: Job, opts: StyleOptions) -> list[asyncio.Task[SegmentResult]]:
        def local_pairs(seg: Segment) -> list[tuple[int, int]]:
            g2l = {g: i for i, g in enumerate(seg.local_to_global)}
            return [(g2l[a], g2l[b]) for a, b in job.masked.pairs if a in g2l and b in g2l]

        return [asyncio.create_task(self._rewrite_segment(s, opts, local_pairs(s))) for s in job.segments]

    def _assemble(self, job: Job, results: list[SegmentResult]) -> dict:
        wanted = [r for r in results if r.seg.rewrite]
        failed = [r for r in wanted if r.status == "error"]
        if wanted and len(failed) == len(wanted):
            raise ProviderError(failed[0].error)

        spans = job.masked.spans
        out_parts: list[str] = []
        seg_out: list[dict] = []
        number = 0
        for k, r in enumerate(results):
            original = protect.unmask(globalise(r.seg.body, r.seg.local_to_global), spans)
            rewritten = protect.unmask(globalise(r.output_local, r.seg.local_to_global), spans)
            out_parts.append(r.seg.lead + rewritten + r.seg.trail)
            if k < len(job.separators):
                out_parts.append(job.separators[k])
            if r.seg.body.strip():
                number += 1
                seg_out.append({
                    "index": r.seg.index,
                    "number": number,
                    "original": original,
                    "output": rewritten,
                    "status": r.status,
                    "similarity": similarity(r.seg.body, r.output_local),
                    "issues": [i.as_dict() for i in r.issues],
                })

        output = "".join(out_parts)
        masked_out = " ".join(r.output_local for r in results)
        return {
            "input": job.text,
            "output": output,
            "segments": seg_out,
            "diff": word_diff(job.text, output),
            "metrics": {
                "words_in": word_count(job.masked.text),
                "words_out": word_count(masked_out),
                "similarity": similarity(job.masked.text, masked_out),
                "protected_spans": len(spans),
                "segments_total": len(seg_out),
                "segments_rewritten": sum(1 for s in seg_out if s["status"] == "rewritten"),
                "readability_in": flesch_reading_ease(job.masked.text),
                "readability_out": flesch_reading_ease(masked_out),
                "elapsed_ms": int((time.perf_counter() - job.started) * 1000),
                "detected_format": job.detected,
            },
            "provider": self.provider.name,
            "model": self.provider.model,
            "demo": self.provider.is_demo,
        }

    async def run(self, text: str, fmt: str, opts: StyleOptions) -> dict:
        job = self._prepare(text, fmt)
        results = await asyncio.gather(*self._tasks(job, opts))
        return self._assemble(job, list(results))

    async def stream(self, text: str, fmt: str, opts: StyleOptions, heartbeat: float = 10.0) -> AsyncIterator[dict]:
        """Yield progress events, then the final result.

        Events: start → progress (one per finished paragraph, with heartbeats
        in between so proxies keep the connection open) → result | error.
        """
        job = self._prepare(text, fmt)
        tasks = self._tasks(job, opts)
        total = sum(1 for s in job.segments if s.rewrite)
        yield {"type": "start", "total": total}
        pending = set(tasks)
        done_count = 0
        try:
            while pending:
                finished, pending = await asyncio.wait(pending, timeout=heartbeat, return_when=asyncio.FIRST_COMPLETED)
                if not finished:
                    yield {"type": "heartbeat"}
                    continue
                for t in finished:
                    r = t.result()
                    if r.seg.rewrite:
                        done_count += 1
                        yield {"type": "progress", "done": done_count, "total": total, "status": r.status}
            yield {"type": "result", "data": self._assemble(job, [t.result() for t in tasks])}
        except ProviderError as e:
            yield {"type": "error", "message": str(e)}
        finally:
            for t in tasks:  # client disconnected: stop spending model calls
                t.cancel()

    # -- sentence alternatives

    async def alternatives(self, sentence: str, context: str, opts: StyleOptions, count: int) -> list[str]:
        masked = protect.mask(sentence, "auto")
        expected = len(masked.spans)
        async with self.sem:
            raw = await self.provider.complete(
                SYSTEM_PROMPT, alternatives_prompt(masked.text, context, opts, count, expected), temperature=0.8
            )
        candidates = _parse_json_list(raw)
        good: list[str] = []
        for c in candidates:
            c = clean_model_output(c, masked.text)
            if not c or check_placeholders(c, expected, masked.pairs):
                continue
            restored = protect.unmask(c, masked.spans)
            if restored.strip() != sentence.strip() and restored not in good:
                good.append(restored)
        return good[:count]


def _parse_json_list(raw: str) -> list[str]:
    raw = raw.replace("\r\n", "\n")
    if "</think>" in raw:
        raw = raw.rsplit("</think>", 1)[1]
    raw = THINK_RE.sub("", raw).strip()
    m = re.search(r"\[.*\]", raw, re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return [str(x) for x in data if isinstance(x, (str, int, float))]
        except json.JSONDecodeError:
            pass
    # Fallback: numbered or bulleted lines.
    lines = [re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", ln).strip().strip('"') for ln in raw.splitlines()]
    return [ln for ln in lines if len(ln.split()) > 2 and not ln.endswith(":")]
