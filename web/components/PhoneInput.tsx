"use client";

import { useEffect, useState } from "react";

import {
  COUNTRIES,
  DEFAULT_COUNTRY_ISO,
  detectCountryIso,
  findCountry,
  isoToFlagEmoji,
} from "@/lib/countries";

/**
 * Country-code select (auto-detected from the browser locale, defaulting to
 * India, always manually overridable) + national-number input. Reports the
 * composed E.164-ish string ("+91 98765 43210") to the parent via onChange.
 */
export function PhoneInput({
  onChange,
  required,
}: {
  onChange: (value: string) => void;
  required?: boolean;
}) {
  // Deterministic on first render (SSR-safe); corrected to the detected
  // country right after mount so there's no hydration mismatch.
  const [iso, setIso] = useState(DEFAULT_COUNTRY_ISO);
  const [national, setNational] = useState("");

  useEffect(() => {
    setIso(detectCountryIso());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const dialCode = findCountry(iso).dialCode;
    onChange(national ? `${dialCode} ${national}` : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [iso, national]);

  return (
    <div style={{ display: "flex", gap: 8 }}>
      <select
        value={iso}
        onChange={(e) => setIso(e.target.value)}
        aria-label="Country code"
        style={{ width: 118, flex: "none" }}
      >
        {COUNTRIES.map((c) => (
          <option key={c.iso2} value={c.iso2}>
            {isoToFlagEmoji(c.iso2)} {c.dialCode}
          </option>
        ))}
      </select>
      <input
        type="tel"
        inputMode="tel"
        value={national}
        onChange={(e) => setNational(e.target.value.replace(/[^\d\s-]/g, ""))}
        placeholder="98765 43210"
        required={required}
        style={{ flex: 1 }}
      />
    </div>
  );
}
