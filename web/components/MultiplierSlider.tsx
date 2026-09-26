"use client";

import { useEffect, useState } from "react";

const PRESETS = [1, 2, 3, 5, 10] as const;

/** Manual lot-size multiplier picker: quick 1/2/3/5/10X preset buttons above
 * a 1X-100X slider + number box for anything in between. Replaces the old
 * fixed 1/2/3/5/10/20 button-only set now that the backend accepts any
 * integer multiplier from 1 to 100 (marketplace.set_my_multiplier). A choice
 * beyond what the admin actually granted for this assignment is still
 * rejected server-side on save, with the allowed range in the error message
 * - the lot preview also clamps to it (protrix_contracts.money.compute_lot),
 * so the number shown never overstates what would actually trade. */
export function MultiplierSlider({
  value,
  onChange,
  disabled,
  min = 1,
  max = 100,
}: {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  min?: number;
  max?: number;
}) {
  // The number box tracks its own raw text while being edited - a fully
  // controlled `value={clamp(...)}` would re-snap on every keystroke,
  // making it impossible to backspace/clear before typing a new value.
  // Clamping (and reset-to-min/max) only happens once editing finishes.
  const [text, setText] = useState(String(value));

  useEffect(() => {
    setText(String(value));
  }, [value]);

  function clamp(n: number): number {
    if (!Number.isFinite(n)) return min;
    return Math.min(max, Math.max(min, Math.round(n)));
  }

  function commitText(raw: string) {
    const parsed = Number(raw);
    const finalValue = raw.trim() === "" ? min : clamp(parsed);
    setText(String(finalValue));
    onChange(finalValue);
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
        {PRESETS.map((m) => (
          <button
            key={m}
            type="button"
            className={value === m ? "btn-primary" : "secondary"}
            disabled={disabled}
            onClick={() => onChange(m)}
            style={{ flex: "1 1 50px" }}
          >
            {m}X
          </button>
        ))}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <input
          type="range"
          min={min}
          max={max}
          step={1}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(clamp(Number(e.target.value)))}
          style={{ flex: 1, accentColor: "var(--accent-blue, #4f7dfb)" }}
          aria-label="Exposure multiplier"
        />
        <input
          type="number"
          min={min}
          max={max}
          step={1}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onBlur={(e) => commitText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          }}
          style={{ width: 56, textAlign: "center", padding: "4px 2px", fontWeight: 700 }}
          aria-label="Exposure multiplier (exact value)"
        />
        <span style={{ fontWeight: 700, color: "var(--muted)", flex: "0 0 auto" }}>X</span>
      </div>
    </div>
  );
}
