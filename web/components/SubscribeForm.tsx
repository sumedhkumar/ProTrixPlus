"use client";

import { useState } from "react";

import { PhoneInput } from "@/components/PhoneInput";

const PACKAGES: { key: string; label: string }[] = [
  { key: "PLAN_3M", label: "3-Month" },
  { key: "PLAN_6M", label: "6-Month" },
  { key: "PLAN_12M", label: "1-Year" },
];

export function SubscribeForm({
  initialPackage,
  identity,
}: {
  initialPackage: string;
  identity: { name: string; email: string } | null;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const [pkg, setPkg] = useState(initialPackage);
  const [name, setName] = useState(identity?.name ?? "");
  const [email, setEmail] = useState(identity?.email ?? "");
  const [phone, setPhone] = useState("");
  const [utrReference, setUtrReference] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);

    const endpoint = identity ? "/api/me/payments/submit" : "/api/payments/submit";
    const body = identity
      ? { name, phone, package: pkg, utr_reference: utrReference }
      : { name, email, phone, package: pkg, utr_reference: utrReference };

    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      const respBody = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(respBody.detail ?? `submission failed (${res.status})`);
      return;
    }
    setDone(true);
  }

  if (done) {
    return (
      <div>
        <div className="card-head">
          <span className="card-title">✓ Submitted</span>
        </div>
        <p style={{ color: "var(--fg)", fontSize: 14, marginBottom: 8 }}>
          Thanks - your payment reference has been submitted.
        </p>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>
          An admin will review it and email you next steps
          {identity ? " once confirmed." : " - including your login details if this is a new account."}
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={(e) => void submit(e)} style={{ display: "grid", gap: 14 }}>
      <div className="card-head">
        <span className="card-title">Submit payment reference</span>
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          Package
        </label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {PACKAGES.map((p) => (
            <button
              key={p.key}
              type="button"
              className={`chip-btn${pkg === p.key ? " active" : ""}`}
              onClick={() => setPkg(p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          Name
        </label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          style={{ width: "100%" }}
        />
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          ✉ Email
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          disabled={identity !== null}
          style={{ width: "100%" }}
        />
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          📱 Phone / WhatsApp
        </label>
        <PhoneInput onChange={setPhone} required />
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          Transaction / UTR reference
        </label>
        <input
          value={utrReference}
          onChange={(e) => setUtrReference(e.target.value)}
          placeholder="e.g. UTR1234567890"
          required
          style={{ width: "100%" }}
        />
      </div>

      <button
        type="submit"
        className="btn-primary"
        disabled={busy}
        style={{ justifyContent: "center", padding: 12 }}
      >
        {busy ? "..." : "Submit for Review →"}
      </button>

      {error ? (
        <p style={{ color: "var(--bad)" }} role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
