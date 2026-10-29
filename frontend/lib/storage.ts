import type { ParaphraseResult, Settings } from "./types";

const SETTINGS_KEY = "recast.settings.v1";
const HISTORY_KEY = "recast.history.v1";
const HISTORY_LIMIT = 15;

export interface HistoryEntry {
  id: string;
  at: number;
  input: string;
  settings: Settings;
  result: ParaphraseResult;
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or blocked: history is a convenience, so ignore */
  }
}

export const loadSettings = (fallback: Settings): Settings => ({ ...fallback, ...read<Partial<Settings>>(SETTINGS_KEY, {}) });
export const saveSettings = (s: Settings) => write(SETTINGS_KEY, s);

export const loadHistory = (): HistoryEntry[] => read<HistoryEntry[]>(HISTORY_KEY, []);

export function addHistory(entry: Omit<HistoryEntry, "id" | "at">): HistoryEntry[] {
  const next = [{ ...entry, id: crypto.randomUUID(), at: Date.now() }, ...loadHistory()].slice(0, HISTORY_LIMIT);
  write(HISTORY_KEY, next);
  return next;
}

export function clearHistory(): void {
  write(HISTORY_KEY, []);
}
