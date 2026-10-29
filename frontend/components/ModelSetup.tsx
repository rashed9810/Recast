"use client";

import { useEffect, useRef, useState } from "react";
import { getModelConfig, listModels, saveModelConfig, testModel } from "@/lib/api";
import type { ModelConfigInput, ModelTestResult, ProviderKind } from "@/lib/types";

interface Preset {
  id: string;
  label: string;
  provider: ProviderKind;
  baseUrl: string;
  needsKey: boolean;
  keyUrl?: string;
  concurrency: number;
  help: string;
  modelHint: string;
}

const PRESETS: Preset[] = [
  {
    id: "ollama",
    label: "Ollama, on this computer (free, private)",
    provider: "openai",
    baseUrl: "http://localhost:11434/v1",
    needsKey: false,
    concurrency: 1,
    help: "Free with no usage limits, and your text never leaves your computer. Install Ollama from ollama.com, then download a model in a terminal, for example: ollama pull qwen2.5:7b-instruct. Larger models (14B and up) write noticeably better academic prose if your computer can run them.",
    modelHint: "qwen2.5:7b-instruct",
  },
  {
    id: "lmstudio",
    label: "LM Studio, on this computer (free, private)",
    provider: "openai",
    baseUrl: "http://localhost:1234/v1",
    needsKey: false,
    concurrency: 1,
    help: "Download a model in LM Studio, then open the Developer tab and start the server.",
    modelHint: "the model id shown in LM Studio",
  },
  {
    id: "groq",
    label: "Groq (free tier, very fast)",
    provider: "openai",
    baseUrl: "https://api.groq.com/openai/v1",
    needsKey: true,
    keyUrl: "https://console.groq.com/keys",
    concurrency: 2,
    help: "Create a free API key, paste it below, then click Load models. Free tiers have rate limits per minute; keep parallel requests low.",
    modelHint: "pick a large instruct model from the list",
  },
  {
    id: "gemini",
    label: "Google Gemini (free tier)",
    provider: "openai",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    needsKey: true,
    keyUrl: "https://aistudio.google.com/apikey",
    concurrency: 2,
    help: "Create a free API key in Google AI Studio, paste it below, then click Load models and choose a 'flash' or 'pro' model.",
    modelHint: "a gemini flash or pro model",
  },
  {
    id: "openrouter",
    label: "OpenRouter (many models, some free)",
    provider: "openai",
    baseUrl: "https://openrouter.ai/api/v1",
    needsKey: true,
    keyUrl: "https://openrouter.ai/keys",
    concurrency: 2,
    help: "One key gives access to models from many companies. Model ids ending in ':free' cost nothing but have tight limits.",
    modelHint: "provider/model-name",
  },
  {
    id: "openai",
    label: "OpenAI",
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    needsKey: true,
    keyUrl: "https://platform.openai.com/api-keys",
    concurrency: 3,
    help: "Paid per use.",
    modelHint: "a current GPT model",
  },
  {
    id: "anthropic",
    label: "Anthropic Claude",
    provider: "anthropic",
    baseUrl: "https://api.anthropic.com",
    needsKey: true,
    keyUrl: "https://console.anthropic.com/settings/keys",
    concurrency: 3,
    help: "Paid per use.",
    modelHint: "a current Claude model",
  },
  {
    id: "custom",
    label: "Other OpenAI-compatible server",
    provider: "openai",
    baseUrl: "",
    needsKey: false,
    concurrency: 2,
    help: "vLLM, llama.cpp server, Together, or any service that offers an OpenAI-style /v1/chat/completions endpoint. Add a key only if the server needs one.",
    modelHint: "model id",
  },
  {
    id: "demo",
    label: "Demo (no AI; swaps a few words)",
    provider: "demo",
    baseUrl: "",
    needsKey: false,
    concurrency: 1,
    help: "Only for trying the interface. It does not paraphrase.",
    modelHint: "",
  },
];

const presetById = (id: string) => PRESETS.find((p) => p.id === id) ?? PRESETS[PRESETS.length - 2];

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export function ModelSetup({ open, onClose, onSaved }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [preset, setPreset] = useState<Preset>(PRESETS[0]);
  const [baseUrl, setBaseUrl] = useState(PRESETS[0].baseUrl);
  const [apiKey, setApiKey] = useState("");
  const [savedKeyHint, setSavedKeyHint] = useState("");
  const [savedService, setSavedService] = useState("");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [concurrency, setConcurrency] = useState(1);
  const [temperature, setTemperature] = useState(0.4);
  const [timeoutS, setTimeoutS] = useState(300);
  const [busy, setBusy] = useState<"" | "models" | "test" | "save">("");
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [test, setTest] = useState<ModelTestResult | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      setMessage(null);
      setTest(null);
      setModels([]);
      getModelConfig()
        .then((c) => {
          const p = presetById(c.preset === "demo" && c.provider !== "demo" ? "custom" : c.preset);
          setPreset(p);
          setBaseUrl(c.base_url || p.baseUrl);
          setModel(c.model);
          setConcurrency(c.concurrency);
          setTemperature(c.temperature);
          setTimeoutS(c.timeout_seconds);
          setSavedKeyHint(c.has_key ? c.key_hint || "saved" : "");
          setSavedService(`${c.provider}|${(c.base_url || "").replace(/\/$/, "")}`);
          setApiKey("");
          if (c.error) setMessage({ kind: "error", text: c.error });
        })
        .catch((e) => setMessage({ kind: "error", text: (e as Error).message }));
    } else if (!open && d.open) {
      d.close();
    }
  }, [open]);

  const choosePreset = (id: string) => {
    const p = presetById(id);
    setPreset(p);
    setBaseUrl(p.baseUrl);
    setModel("");
    setModels([]);
    setApiKey("");
    setConcurrency(p.concurrency);
    setMessage(null);
    setTest(null);
  };

  const sameServiceAsSaved = savedService === `${preset.provider}|${baseUrl.replace(/\/$/, "")}`;
  const keyStillSaved = sameServiceAsSaved && !!savedKeyHint;

  const config = (): ModelConfigInput => ({
    provider: preset.provider,
    preset: preset.id,
    base_url: baseUrl.trim(),
    api_key: apiKey.trim() ? apiKey.trim() : keyStillSaved ? undefined : "",
    model: model.trim(),
    temperature,
    concurrency,
    timeout_seconds: timeoutS,
  });

  const missing = (): string => {
    if (preset.provider === "demo") return "";
    if (!baseUrl.trim()) return "Enter the server address.";
    if (preset.needsKey && !apiKey.trim() && !keyStillSaved) return "Paste your API key first.";
    return "";
  };

  const loadModels = async () => {
    const m = missing();
    if (m) return setMessage({ kind: "error", text: m });
    setBusy("models");
    setMessage(null);
    try {
      const { models } = await listModels(config());
      setModels(models);
      if (!models.length) setMessage({ kind: "error", text: "The server returned no models. For Ollama, download one first: ollama pull qwen2.5:7b-instruct" });
      else {
        if (!model || !models.includes(model)) setModel(models[0]);
        setMessage({ kind: "ok", text: `Found ${models.length} model${models.length === 1 ? "" : "s"}.` });
      }
    } catch (e) {
      setMessage({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const runTest = async () => {
    const m = missing() || (preset.provider !== "demo" && !model.trim() ? "Choose a model first." : "");
    if (m) return setMessage({ kind: "error", text: m });
    setBusy("test");
    setMessage(null);
    setTest(null);
    try {
      const r = await testModel(config());
      setTest(r);
      setMessage(
        r.ok
          ? { kind: "ok", text: `It works. Answered in ${(r.ms / 1000).toFixed(1)} s.` }
          : { kind: "error", text: "The model answered but broke the protected LaTeX. It may still work, but a larger model is recommended." },
      );
    } catch (e) {
      setMessage({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const save = async () => {
    const m = missing() || (preset.provider !== "demo" && !model.trim() ? "Choose a model first." : "");
    if (m) return setMessage({ kind: "error", text: m });
    setBusy("save");
    try {
      await saveModelConfig(config());
      onSaved();
      onClose();
    } catch (e) {
      setMessage({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const isDemo = preset.provider === "demo";

  return (
    <dialog ref={ref} className="setup" onClose={onClose} aria-labelledby="setup-title">
      <form method="dialog" className="setup-inner" onSubmit={(e) => e.preventDefault()}>
        <header className="setup-head">
          <h2 id="setup-title">Model setup</h2>
          <button type="button" className="ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <label className="field">
          <span>Service</span>
          <select value={preset.id} onChange={(e) => choosePreset(e.target.value)}>
            {PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <p className="setup-help">
          {preset.help}{" "}
          {preset.keyUrl && (
            <a href={preset.keyUrl} target="_blank" rel="noreferrer">
              Get a key
            </a>
          )}
        </p>
        {preset.needsKey && preset.id !== "openai" && preset.id !== "anthropic" && (
          <p className="setup-note">
            Free cloud tiers may use what you send to improve their models. For unpublished work, a model on your own computer is the
            private option.
          </p>
        )}

        {!isDemo && (
          <>
            <label className="field">
              <span>Server address</span>
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://localhost:11434/v1" spellCheck={false} />
            </label>

            {(preset.needsKey || preset.id === "custom") && (
              <label className="field">
                <span>API key</span>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={keyStillSaved ? `Saved key ${savedKeyHint}. Leave empty to keep it.` : "Paste your key"}
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
            )}

            <div className="field">
              <label htmlFor="model-input">Model</label>
              <div className="model-row">
                <input
                  id="model-input"
                  list="model-options"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder={preset.modelHint}
                  spellCheck={false}
                />
                <datalist id="model-options">
                  {models.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
                <button type="button" className="ghost bordered" onClick={loadModels} disabled={!!busy}>
                  {busy === "models" ? "Loading…" : "Load models"}
                </button>
              </div>
              {models.length > 0 && (
                <select className="model-select" value={models.includes(model) ? model : ""} onChange={(e) => setModel(e.target.value)} aria-label="Available models">
                  <option value="" disabled>
                    Choose from {models.length} available models
                  </option>
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <details className="setup-adv">
              <summary>Advanced</summary>
              <div className="adv-grid">
                <label className="field">
                  <span>Parallel requests</span>
                  <input type="number" min={1} max={8} value={concurrency} onChange={(e) => setConcurrency(Math.min(8, Math.max(1, Number(e.target.value) || 1)))} />
                  <small>Use 1 for a model on your computer.</small>
                </label>
                <label className="field">
                  <span>Creativity</span>
                  <input type="number" min={0} max={1.5} step={0.1} value={temperature} onChange={(e) => setTemperature(Math.min(1.5, Math.max(0, Number(e.target.value) || 0)))} />
                  <small>0.2–0.5 keeps meaning tight.</small>
                </label>
                <label className="field">
                  <span>Time limit per paragraph (s)</span>
                  <input type="number" min={10} max={1800} value={timeoutS} onChange={(e) => setTimeoutS(Math.min(1800, Math.max(10, Number(e.target.value) || 300)))} />
                  <small>Raise this for slow computers.</small>
                </label>
              </div>
            </details>
          </>
        )}

        {message && (
          <p className={message.kind === "ok" ? "setup-msg ok" : "setup-msg error"} role="status">
            {message.text}
          </p>
        )}
        {test && (
          <div className="setup-test">
            <p className="small muted">Test sentence, rewritten with the Fluency mode:</p>
            <p className="manuscript">{test.output}</p>
          </div>
        )}

        <footer className="setup-foot">
          <button type="button" className="ghost bordered" onClick={runTest} disabled={!!busy}>
            {busy === "test" ? "Testing… (local models can take a minute)" : "Test"}
          </button>
          <button type="button" className="primary" onClick={save} disabled={!!busy}>
            {busy === "save" ? "Saving…" : "Save and use"}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
