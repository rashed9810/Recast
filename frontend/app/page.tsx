"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Controls } from "@/components/Controls";
import { ModelSetup } from "@/components/ModelSetup";
import { OutputPanel } from "@/components/OutputPanel";
import { getHealth, getModes, paraphrase, type Progress } from "@/lib/api";
import { countWords } from "@/lib/latex";
import { SAMPLE_TEXT } from "@/lib/sample";
import { addHistory, clearHistory, loadHistory, loadSettings, saveSettings, type HistoryEntry } from "@/lib/storage";
import type { Health, ModeInfo, ParaphraseResult, SegmentResult, Settings } from "@/lib/types";

const DEFAULT_SETTINGS: Settings = {
  mode: "academic",
  strength: 2,
  dialect: "en-US",
  voice: "keep",
  field: "",
  frozen_terms: [],
  format: "auto",
};

const FALLBACK_MODES: ModeInfo[] = [
  { id: "academic", label: "Academic", description: "Formal, precise register for papers and theses." },
  { id: "standard", label: "Standard", description: "Fresh wording with the same meaning and tone." },
  { id: "fluency", label: "Fluency", description: "Minimal edits: grammar, articles, awkward phrasing." },
  { id: "concise", label: "Concise", description: "Cut redundancy and wordiness." },
  { id: "expand", label: "Elaborate", description: "Smoother, more explicit flow without new facts." },
  { id: "simplify", label: "Simplify", description: "Plainer language for broad readers." },
];

export default function Home() {
  const [input, setInput] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [modes, setModes] = useState<ModeInfo[]>(FALLBACK_MODES);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [result, setResult] = useState<ParaphraseResult | null>(null);
  const [output, setOutput] = useState("");
  const [reverted, setReverted] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refreshHealth = useCallback(() => {
    getHealth()
      .then((h) => {
        setHealth(h);
        setHealthError(false);
      })
      .catch(() => setHealthError(true));
  }, []);

  useEffect(() => {
    setSettings(loadSettings(DEFAULT_SETTINGS));
    setHistory(loadHistory());
    refreshHealth();
    getModes().then(setModes).catch(() => undefined);
  }, [refreshHealth]);

  // While the backend is offline, keep checking so the app recovers by itself.
  useEffect(() => {
    if (!healthError) return;
    const id = setInterval(() => {
      refreshHealth();
      getModes().then(setModes).catch(() => undefined);
    }, 5000);
    return () => clearInterval(id);
  }, [healthError, refreshHealth]);

  const updateSettings = (patch: Partial<Settings>) =>
    setSettings((s) => {
      const next = { ...s, ...patch };
      saveSettings(next);
      return next;
    });

  const run = useCallback(async () => {
    if (!input.trim() || loading) return;
    abortRef.current = new AbortController();
    setLoading(true);
    setProgress(null);
    setError("");
    try {
      const res = await paraphrase(input, settings, setProgress, abortRef.current.signal);
      setResult(res);
      setOutput(res.output);
      setReverted(new Set());
      setHistory(addHistory({ input, settings, result: res }));
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setLoading(false);
      setProgress(null);
    }
  }, [input, settings, loading]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        run();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [run]);

  const revertSegment = (seg: SegmentResult): boolean => {
    const at = output.indexOf(seg.output);
    if (at < 0) return false;
    setOutput(output.slice(0, at) + seg.original + output.slice(at + seg.output.length));
    setReverted((r) => new Set(r).add(seg.index));
    return true;
  };

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    setInput(await f.text());
    setFileName(f.name);
  };

  const download = () => {
    const ext = fileName?.match(/\.[a-z]+$/i)?.[0] ?? (result?.metrics.detected_format === "latex" ? ".tex" : ".txt");
    const base = fileName ? fileName.replace(/\.[a-z]+$/i, "") : "rewrite";
    const url = URL.createObjectURL(new Blob([output], { type: "text/plain;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `${base}-recast${ext}` });
    a.click();
    URL.revokeObjectURL(url);
  };

  const restore = (h: HistoryEntry) => {
    setInput(h.input);
    updateSettings(h.settings);
    setResult(h.result);
    setOutput(h.result.output);
    setReverted(new Set());
  };

  const tooLong = health ? input.length > health.max_input_chars : false;
  const words = countWords(input);
  const m = result?.metrics;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>
            R
          </span>
          <span className="name">Recast</span>
          <span className="tagline">Rewrite research prose. Keep the science and the LaTeX intact.</span>
        </div>
        <div className="status-area">
          <History items={history} onPick={restore} onClear={() => (clearHistory(), setHistory([]))} />
          <ModelStatus health={health} failed={healthError} onClick={() => setSetupOpen(true)} />
        </div>
      </header>

      <Controls modes={modes} settings={settings} onChange={updateSettings} />

      <main className="desk">
        <div className="sheet sheet-in">
          <div className="sheet-head">
            <label htmlFor="source" className="sheet-title">
              Original{fileName && <span className="file-name">{fileName}</span>}
            </label>
            <div className="head-actions">
              <button type="button" className="ghost" onClick={() => fileRef.current?.click()}>
                Open file
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".tex,.txt,.md,.bib,text/plain"
                hidden
                onChange={(e) => onFile(e.target.files?.[0])}
              />
              {!input && (
                <button type="button" className="ghost" onClick={() => setInput(SAMPLE_TEXT)}>
                  Try a sample
                </button>
              )}
              {input && (
                <button
                  type="button"
                  className="ghost"
                  onClick={() => {
                    setInput("");
                    setFileName(null);
                  }}
                >
                  Clear
                </button>
              )}
            </div>
          </div>
          <textarea
            id="source"
            className="manuscript source"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Paste a paragraph, a section, or a whole .tex file."
            spellCheck
          />
          <div className="sheet-foot">
            <span className={tooLong ? "error small" : "muted small"}>
              {tooLong ? `Too long: limit is ${health?.max_input_chars.toLocaleString()} characters` : `${words.toLocaleString()} words of prose`}
            </span>
            <div className="run-group">
              {loading && (
                <button type="button" className="ghost" onClick={() => abortRef.current?.abort()}>
                  Stop
                </button>
              )}
              <button type="button" className="primary" onClick={run} disabled={!input.trim() || loading || tooLong}>
                {loading ? "Rewriting…" : "Rewrite"}
                <kbd>Ctrl ↵</kbd>
              </button>
            </div>
          </div>
        </div>

        <OutputPanel
          result={result}
          output={output}
          loading={loading}
          settings={settings}
          progress={progress}
          demo={!!health?.demo}
          onOpenSetup={() => setSetupOpen(true)}
          onOutputChange={setOutput}
          onRevertSegment={revertSegment}
          revertedSegments={reverted}
        />
      </main>

      {error && (
        <p className="banner-error" role="alert">
          {error}
          {/model|server|key|rate limit|reach/i.test(error) && (
            <button type="button" className="ghost bordered" onClick={() => setSetupOpen(true)}>
              Open model setup
            </button>
          )}
        </p>
      )}

      <ModelSetup open={setupOpen} onClose={() => setSetupOpen(false)} onSaved={refreshHealth} />

      {m && !loading && (
        <footer className="metrics">
          <dl>
            <div>
              <dt>Words</dt>
              <dd>
                {m.words_in} → {m.words_out}
              </dd>
            </div>
            <div>
              <dt>Wording kept</dt>
              <dd>{Math.round(m.similarity * 100)}%</dd>
            </div>
            <div>
              <dt>Locked items</dt>
              <dd>{m.protected_spans}</dd>
            </div>
            <div>
              <dt>Paragraphs rewritten</dt>
              <dd>
                {m.segments_rewritten} of {m.segments_total}
              </dd>
            </div>
            {m.readability_in !== null && m.readability_out !== null && (
              <div title="Flesch reading ease: higher is easier to read. Academic prose usually scores 10–40.">
                <dt>Reading ease</dt>
                <dd>
                  {m.readability_in} → {m.readability_out}
                </dd>
              </div>
            )}
            <div>
              <dt>Time</dt>
              <dd>{(m.elapsed_ms / 1000).toFixed(1)} s</dd>
            </div>
          </dl>
          <button type="button" className="ghost" onClick={download}>
            Download {fileName?.match(/\.[a-z]+$/i)?.[0] ?? (m.detected_format === "latex" ? ".tex" : ".txt")}
          </button>
        </footer>
      )}
    </div>
  );
}

function ModelStatus({ health, failed, onClick }: { health: Health | null; failed: boolean; onClick: () => void }) {
  let cls = "model";
  let label = "Connecting…";
  let title = "Model setup";
  if (failed) {
    cls += " model-down";
    label = "Backend offline";
    title = "Start the backend: uvicorn app.main:app --port 8000";
  } else if (health?.demo) {
    cls += " model-demo";
    label = health.config_error ? "Model setup needs attention" : "Demo mode: set up a model";
    title = health.config_error || "No AI model is connected.";
  } else if (health) {
    cls += " model-ok";
    label = health.model;
    title = `Connected via ${health.provider}. Click to change.`;
  }
  return (
    <button type="button" className={cls} title={title} onClick={failed ? undefined : onClick}>
      {label}
    </button>
  );
}

function History({ items, onPick, onClear }: { items: HistoryEntry[]; onPick: (h: HistoryEntry) => void; onClear: () => void }) {
  if (!items.length) return null;
  return (
    <details className="history">
      <summary>Recent</summary>
      <div className="history-menu">
        <ul>
          {items.map((h) => (
            <li key={h.id}>
              <button type="button" onClick={(e) => (onPick(h), (e.currentTarget.closest("details") as HTMLDetailsElement).removeAttribute("open"))}>
                <span className="h-text">{h.input.slice(0, 70)}</span>
                <span className="muted small">
                  {new Date(h.at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <button type="button" className="ghost small-btn" onClick={onClear}>
          Clear history
        </button>
      </div>
    </details>
  );
}
