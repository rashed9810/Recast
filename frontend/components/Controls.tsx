"use client";

import { useState } from "react";
import type { ModeInfo, Settings } from "@/lib/types";
import { TermsInput } from "./TermsInput";

interface Props {
  modes: ModeInfo[];
  settings: Settings;
  onChange: (patch: Partial<Settings>) => void;
}

const STRENGTH_LABEL = { 1: "Light", 2: "Balanced", 3: "Strong" } as const;

export function Controls({ modes, settings, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const active = modes.find((m) => m.id === settings.mode);

  return (
    <section className="controls" aria-label="Rewrite settings">
      <div className="controls-row">
        <div className="modes" role="radiogroup" aria-label="Mode">
          {modes.map((m) => (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={settings.mode === m.id}
              className={settings.mode === m.id ? "mode is-active" : "mode"}
              onClick={() => onChange({ mode: m.id })}
              title={m.description}
            >
              {m.label}
            </button>
          ))}
        </div>

        <label className="strength">
          <span>Change</span>
          <input
            type="range"
            min={1}
            max={3}
            step={1}
            value={settings.strength}
            onChange={(e) => onChange({ strength: Number(e.target.value) as 1 | 2 | 3 })}
            aria-valuetext={STRENGTH_LABEL[settings.strength]}
          />
          <output>{STRENGTH_LABEL[settings.strength]}</output>
        </label>

        <button
          type="button"
          className="link-btn"
          aria-expanded={open}
          aria-controls="more-settings"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Fewer options" : "More options"}
          {settings.frozen_terms.length > 0 && !open && <span className="badge">{settings.frozen_terms.length} locked</span>}
        </button>
      </div>

      {active && <p className="mode-hint">{active.description}</p>}

      {open && (
        <div id="more-settings" className="more">
          <label>
            <span>Spelling</span>
            <select value={settings.dialect} onChange={(e) => onChange({ dialect: e.target.value as Settings["dialect"] })}>
              <option value="en-US">American English</option>
              <option value="en-GB">British English</option>
              <option value="keep">Keep as written</option>
            </select>
          </label>
          <label>
            <span>Voice</span>
            <select value={settings.voice} onChange={(e) => onChange({ voice: e.target.value as Settings["voice"] })}>
              <option value="keep">Keep as written</option>
              <option value="active">Prefer active (“we propose”)</option>
              <option value="passive">Prefer impersonal (“it is proposed”)</option>
            </select>
          </label>
          <label>
            <span>Input type</span>
            <select value={settings.format} onChange={(e) => onChange({ format: e.target.value as Settings["format"] })}>
              <option value="auto">Detect automatically</option>
              <option value="latex">LaTeX source</option>
              <option value="plain">Plain text</option>
            </select>
          </label>
          <label>
            <span>Field</span>
            <input
              value={settings.field}
              maxLength={80}
              onChange={(e) => onChange({ field: e.target.value })}
              placeholder="e.g. medical imaging"
            />
          </label>
          <div className="more-wide">
            <label htmlFor="terms">
              <span>Locked terms</span>
              <small>Kept exactly as written. Press Enter after each one.</small>
            </label>
            <TermsInput terms={settings.frozen_terms} onChange={(frozen_terms) => onChange({ frozen_terms })} />
          </div>
        </div>
      )}
    </section>
  );
}
