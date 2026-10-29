export type ModeId = "academic" | "standard" | "fluency" | "concise" | "expand" | "simplify";
export type Dialect = "en-US" | "en-GB" | "keep";
export type Voice = "keep" | "active" | "passive";
export type InputFormat = "auto" | "latex" | "plain";

export interface Settings {
  mode: ModeId;
  strength: 1 | 2 | 3;
  dialect: Dialect;
  voice: Voice;
  field: string;
  frozen_terms: string[];
  format: InputFormat;
}

export interface Issue {
  level: "error" | "warning" | "info";
  code: string;
  message: string;
}

export interface SegmentResult {
  index: number;
  number: number;
  original: string;
  output: string;
  status: "rewritten" | "skipped" | "fallback" | "error";
  similarity: number;
  issues: Issue[];
}

export interface DiffOp {
  op: "equal" | "insert" | "delete";
  text: string;
}

export interface Metrics {
  words_in: number;
  words_out: number;
  similarity: number;
  protected_spans: number;
  segments_total: number;
  segments_rewritten: number;
  readability_in: number | null;
  readability_out: number | null;
  elapsed_ms: number;
  detected_format: "latex" | "plain";
}

export interface ParaphraseResult {
  input: string;
  output: string;
  segments: SegmentResult[];
  diff: DiffOp[];
  metrics: Metrics;
  provider: string;
  model: string;
  demo: boolean;
}

export interface Health {
  status: string;
  provider: string;
  model: string;
  demo: boolean;
  max_input_chars: number;
  config_error: string;
}

export interface ModeInfo {
  id: ModeId;
  label: string;
  description: string;
}

export type ProviderKind = "openai" | "anthropic" | "demo";

export interface ModelConfig {
  provider: ProviderKind;
  preset: string;
  base_url: string;
  model: string;
  temperature: number;
  concurrency: number;
  timeout_seconds: number;
  max_tokens: number;
  has_key: boolean;
  key_hint: string;
  error: string;
}

export interface ModelConfigInput {
  provider: ProviderKind;
  preset: string;
  base_url: string;
  /** undefined = keep the saved key; "" = remove it */
  api_key?: string;
  model: string;
  temperature: number;
  concurrency: number;
  timeout_seconds: number;
}

export interface ModelTestResult {
  ok: boolean;
  ms: number;
  input: string;
  output: string;
  issues: Issue[];
}
