import type { Health, ModeInfo, ModelConfig, ModelConfigInput, ModelTestResult, ParaphraseResult, Settings } from "./types";

async function errorFrom(res: Response): Promise<Error> {
  let detail = `Request failed (${res.status}).`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    if (res.status >= 500) detail = "The Recast backend failed. Check the terminal where it is running for details.";
  }
  return new Error(detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new Error("Can't reach the Recast app server. Is `npm run dev` still running?");
  }
  if (!res.ok) throw await errorFrom(res);
  return res.json() as Promise<T>;
}

export const getHealth = () => request<Health>("/api/health");
export const getModes = () => request<ModeInfo[]>("/api/modes");

export interface Progress {
  done: number;
  total: number;
}

/** Rewrites text, reporting progress paragraph by paragraph. */
export async function paraphrase(
  text: string,
  s: Settings,
  onProgress: (p: Progress) => void,
  signal?: AbortSignal,
): Promise<ParaphraseResult> {
  let res: Response;
  try {
    res = await fetch("/api/paraphrase/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, ...s }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new Error("Can't reach the Recast app server. Is `npm run dev` still running?");
  }
  if (!res.ok || !res.body) throw await errorFrom(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const ev = JSON.parse(line);
      if (ev.type === "start") onProgress({ done: 0, total: ev.total });
      else if (ev.type === "progress") onProgress({ done: ev.done, total: ev.total });
      else if (ev.type === "result") return ev.data as ParaphraseResult;
      else if (ev.type === "error") throw new Error(ev.message);
    }
    if (done) break;
  }
  throw new Error("The connection closed before the rewrite finished. Check the backend terminal for errors.");
}

export const getAlternatives = (sentence: string, context: string, s: Settings) =>
  request<{ alternatives: string[] }>("/api/alternatives", {
    method: "POST",
    body: JSON.stringify({
      sentence,
      context,
      count: 3,
      mode: s.mode,
      strength: s.strength,
      dialect: s.dialect,
      voice: s.voice,
      field: s.field,
      frozen_terms: s.frozen_terms,
    }),
  });

export const getModelConfig = () => request<ModelConfig>("/api/settings/model");
export const saveModelConfig = (c: ModelConfigInput) =>
  request<ModelConfig>("/api/settings/model", { method: "PUT", body: JSON.stringify(c) });
export const listModels = (c: ModelConfigInput) =>
  request<{ models: string[] }>("/api/settings/model/models", { method: "POST", body: JSON.stringify(c) });
export const testModel = (c: ModelConfigInput) =>
  request<ModelTestResult>("/api/settings/model/test", { method: "POST", body: JSON.stringify(c) });
