/**
 * Splits text into prose and LaTeX pieces for display only, so locked
 * content can be highlighted in the rewrite. The backend does the real,
 * stricter protection; this just needs to look right.
 */
export interface Piece {
  text: string;
  locked: boolean;
}

const LOCKED_RE = new RegExp(
  [
    String.raw`%[^\n]*`, // comments
    String.raw`\\begin\{([a-zA-Z*]+)\}[\s\S]*?\\end\{\1\}`, // environments
    String.raw`\$\$[\s\S]+?\$\$`,
    String.raw`\\\[[\s\S]+?\\\]`,
    String.raw`\\\([\s\S]+?\\\)`,
    String.raw`\$(?:\\.|[^$\\])+\$`,
    String.raw`~?\\[a-zA-Z]+\*?(?:\[[^\]]*\])*(?:\{(?:[^{}]|\{[^{}]*\})*\})*`, // commands with args
    String.raw`\\[^a-zA-Z\s]`, // \% \& etc.
    String.raw`https?://[^\s{}]+`,
  ].join("|"),
  "g",
);

export function splitLatex(text: string): Piece[] {
  const pieces: Piece[] = [];
  let last = 0;
  for (const m of text.matchAll(LOCKED_RE)) {
    const start = m.index ?? 0;
    if (start > last) pieces.push({ text: text.slice(last, start), locked: false });
    pieces.push({ text: m[0], locked: true });
    last = start + m[0].length;
  }
  if (last < text.length) pieces.push({ text: text.slice(last), locked: false });
  return pieces;
}

export const countWords = (text: string) =>
  splitLatex(text)
    .filter((p) => !p.locked)
    .map((p) => p.text)
    .join(" ")
    .match(/[A-Za-z][A-Za-z'\-]*/g)?.length ?? 0;
