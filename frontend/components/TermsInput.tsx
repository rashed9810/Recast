"use client";

import { useState, type KeyboardEvent } from "react";

interface Props {
  terms: string[];
  onChange: (terms: string[]) => void;
}

export function TermsInput({ terms, onChange }: Props) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const parts = draft
      .split(/[,;\n]/)
      .map((t) => t.trim())
      .filter((t) => t && !terms.includes(t));
    if (parts.length) onChange([...terms, ...parts]);
    setDraft("");
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && terms.length) {
      onChange(terms.slice(0, -1));
    }
  };

  return (
    <div className="terms">
      {terms.map((t) => (
        <span key={t} className="term">
          {t}
          <button type="button" aria-label={`Unlock ${t}`} onClick={() => onChange(terms.filter((x) => x !== t))}>
            ×
          </button>
        </span>
      ))}
      <input
        id="terms"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={commit}
        placeholder={terms.length ? "Add another" : "e.g. Dice score, Synapse, TransUNet"}
      />
    </div>
  );
}
