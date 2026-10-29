"use client";

import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { getAlternatives, type Progress } from "@/lib/api";
import { splitLatex } from "@/lib/latex";
import type { ParaphraseResult, SegmentResult, Settings } from "@/lib/types";

type Tab = "rewrite" | "changes" | "checks";

interface Props {
  result: ParaphraseResult | null;
  output: string;
  loading: boolean;
  progress: Progress | null;
  demo: boolean;
  onOpenSetup: () => void;
  settings: Settings;
  onOutputChange: (text: string) => void;
  onRevertSegment: (seg: SegmentResult) => boolean;
  revertedSegments: Set<number>;
}

export function OutputPanel(props: Props) {
  const { result, output, loading } = props;
  const [tab, setTab] = useState<Tab>("rewrite");

  const flagged = result?.segments.filter((s) => s.issues.some((i) => i.level !== "info")).length ?? 0;

  return (
    <div className="sheet sheet-out">
      <div className="sheet-head" role="tablist" aria-label="Result views">
        {(["rewrite", "changes", "checks"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            className={tab === t ? "tab is-active" : "tab"}
            onClick={() => setTab(t)}
            disabled={!result}
          >
            {t === "rewrite" ? "Rewrite" : t === "changes" ? "Changes" : "Checks"}
            {t === "checks" && result && (
              <span className={flagged ? "count count-warn" : "count count-ok"}>{flagged || "✓"}</span>
            )}
          </button>
        ))}
      </div>

      <div className="sheet-body" aria-live="polite" aria-busy={loading}>
        {loading && <Working progress={props.progress} />}
        {!loading && !result && <Empty demo={props.demo} onOpenSetup={props.onOpenSetup} />}
        {!loading && result && tab === "rewrite" && <RewriteView {...props} output={output} />}
        {!loading && result && tab === "changes" && <DiffView result={result} />}
        {!loading && result && tab === "checks" && <ChecksView {...props} result={result} />}
      </div>
    </div>
  );
}

function Empty({ demo, onOpenSetup }: { demo: boolean; onOpenSetup: () => void }) {
  if (demo)
    return (
      <div className="empty">
        <p>Connect an AI model to start paraphrasing.</p>
        <p className="muted">
          Recast is running in demo mode, which only swaps a few fixed words to show how the tool works. Real rewriting needs a
          model: a free one on your own computer (Ollama), or a free or paid cloud service.
        </p>
        <button type="button" className="primary" onClick={onOpenSetup}>
          Set up a model
        </button>
      </div>
    );
  return (
    <div className="empty">
      <p>Your rewrite appears here.</p>
      <p className="muted">
        Equations, citations, references and LaTeX commands are locked before the text reaches the model, and restored exactly
        afterwards. Every paragraph is then checked for changed numbers, dropped negations and weakened hedges.
      </p>
    </div>
  );
}

function Working({ progress }: { progress: Progress | null }) {
  const total = progress?.total ?? 0;
  const done = progress?.done ?? 0;
  return (
    <div className="working">
      <div className="working-row">
        <span className="pen" aria-hidden />
        <p>
          {total > 0 ? `Rewriting paragraph ${Math.min(done + 1, total)} of ${total}…` : "Preparing your text…"}
        </p>
      </div>
      {total > 0 && (
        <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
          <span style={{ width: `${(done / total) * 100}%` }} />
        </div>
      )}
      <p className="muted small">Models on your own computer can take 10–60 seconds per paragraph. You can keep reading while it works.</p>
    </div>
  );
}

function Highlighted({ text }: { text: string }) {
  return (
    <>
      {splitLatex(text).map((p, i) =>
        p.locked ? (
          <mark key={i} className="locked" title="Locked: copied from your original">
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  );
}

function RewriteView({ output, settings, onOutputChange }: Props) {
  const [editing, setEditing] = useState(false);
  const [selection, setSelection] = useState<{ text: string; x: number; y: number } | null>(null);
  const [alts, setAlts] = useState<string[] | null>(null);
  const [altError, setAltError] = useState("");
  const [altLoading, setAltLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const clear = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest(".alt-pop, .reading")) closePop();
    };
    document.addEventListener("mousedown", clear);
    return () => document.removeEventListener("mousedown", clear);
  }, []);

  const closePop = () => {
    setSelection(null);
    setAlts(null);
    setAltError("");
  };

  const onMouseUp = (e: ReactMouseEvent) => {
    // Clicks inside the popup must not reset it (that used to swallow the
    // click on an alternative).
    if ((e.target as HTMLElement).closest(".alt-pop")) return;
    const sel = window.getSelection();
    const text = sel?.toString().trim() ?? "";
    if (!sel || !sel.rangeCount || text.split(/\s+/).length < 3 || !bodyRef.current) {
      if (!text) closePop();
      return;
    }
    if (text.length > 1500) return; // whole-page selections are not useful
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    const box = bodyRef.current.getBoundingClientRect();
    setAlts(null);
    setAltError("");
    setSelection({ text, x: rect.left - box.left, y: rect.bottom - box.top + bodyRef.current.scrollTop + 6 });
  };

  const fetchAlts = async () => {
    if (!selection) return;
    setAltLoading(true);
    setAltError("");
    try {
      const para = output.split(/\n\s*\n/).find((p) => p.includes(selection.text)) ?? "";
      const { alternatives } = await getAlternatives(selection.text, para, settings);
      if (alternatives.length) setAlts(alternatives);
      else setAltError("No safe alternatives came back. Try selecting a whole sentence.");
    } catch (e) {
      setAltError((e as Error).message);
    } finally {
      setAltLoading(false);
    }
  };

  const apply = (alt: string) => {
    if (selection) {
      const at = output.indexOf(selection.text);
      if (at >= 0) onOutputChange(output.slice(0, at) + alt + output.slice(at + selection.text.length));
    }
    closePop();
    window.getSelection()?.removeAllRanges();
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(output);
    } catch {
      // Clipboard API is blocked on plain http from other devices: fall back.
      const ta = Object.assign(document.createElement("textarea"), { value: output });
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="rewrite">
      <div className="toolbar">
        <button type="button" className="ghost" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
        <button type="button" className="ghost" onClick={() => setEditing((v) => !v)}>
          {editing ? "Done editing" : "Edit"}
        </button>
        {!editing && <span className="muted small">Select a sentence to see alternatives.</span>}
      </div>
      {editing ? (
        <textarea
          className="manuscript editor"
          value={output}
          onChange={(e) => onOutputChange(e.target.value)}
          aria-label="Edit rewrite"
          spellCheck
        />
      ) : (
        <div ref={bodyRef} className="manuscript reading" onMouseUp={onMouseUp}>
          <Highlighted text={output} />
          {selection && (
            <div className="alt-pop" style={{ left: Math.max(0, selection.x), top: selection.y }} role="dialog" aria-label="Alternatives">
              {!alts && (
                <button type="button" className="primary small-btn" onClick={fetchAlts} disabled={altLoading}>
                  {altLoading ? "Finding alternatives…" : "Suggest alternatives"}
                </button>
              )}
              {altError && <p className="error small">{altError}</p>}
              {alts && (
                <ul>
                  {alts.map((a, i) => (
                    <li key={i}>
                      <button type="button" onClick={() => apply(a)}>
                        <Highlighted text={a} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DiffView({ result }: { result: ParaphraseResult }) {
  return (
    <div className="manuscript diff">
      <p className="legend small">
        <ins>added</ins> <del>removed</del>
      </p>
      {result.diff.map((d, i) =>
        d.op === "insert" ? <ins key={i}>{d.text}</ins> : d.op === "delete" ? <del key={i}>{d.text}</del> : <span key={i}>{d.text}</span>,
      )}
    </div>
  );
}

const STATUS = {
  rewritten: "Rewritten",
  skipped: "Left as is (no prose)",
  fallback: "Original kept",
  error: "Model error: original kept",
} as const;

function ChecksView({ result, onRevertSegment, revertedSegments }: Props & { result: ParaphraseResult }) {
  const [revertError, setRevertError] = useState<number | null>(null);
  const segs = result.segments.filter((s) => s.status !== "skipped");
  const flagged = segs.filter((s) => s.issues.some((i) => i.level !== "info"));
  return (
    <div className="checks">
      <p className="checks-summary">
        {flagged.length === 0
          ? "No automatic check flagged a problem. Still read the rewrite before using it."
          : `${flagged.length} of ${segs.length} paragraphs need a look. Compare each one with your original.`}
      </p>
      <ol className="seg-list">
        {segs.map((s) => {
          const reverted = revertedSegments.has(s.index);
          const serious = s.issues.filter((i) => i.level !== "info");
          return (
            <li key={s.index} className={serious.length ? "seg seg-flag" : "seg"}>
              <div className="seg-top">
                <span className="seg-name">Paragraph {s.number}</span>
                <span className={`status status-${reverted ? "reverted" : s.status === "error" ? "fallback" : s.status}`}>
                  {reverted ? "Original restored" : STATUS[s.status]}
                </span>
                <span className="muted small">{Math.round(s.similarity * 100)}% of wording kept</span>
              </div>
              {s.issues.length > 0 && (
                <ul className="issues">
                  {s.issues.map((i, k) => (
                    <li key={k} className={`issue issue-${i.level}`}>
                      {i.message}
                    </li>
                  ))}
                </ul>
              )}
              <details>
                <summary>Compare</summary>
                <div className="compare">
                  <div>
                    <h4>Original</h4>
                    <p className="manuscript">
                      <Highlighted text={s.original} />
                    </p>
                  </div>
                  <div>
                    <h4>Rewrite</h4>
                    <p className="manuscript">
                      <Highlighted text={s.output} />
                    </p>
                  </div>
                </div>
              </details>
              {s.status === "rewritten" && !reverted && (
                <button
                  type="button"
                  className="ghost small-btn bordered"
                  onClick={() => setRevertError(onRevertSegment(s) ? null : s.index)}
                >
                  Use original paragraph
                </button>
              )}
              {revertError === s.index && (
                <p className="error small">You edited this paragraph, so it can't be swapped automatically. Copy the original from Compare.</p>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
