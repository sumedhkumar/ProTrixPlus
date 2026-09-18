"use client";

import { useState } from "react";

import { PhoneInput } from "@/components/PhoneInput";

export function TrialSignupForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/trial-signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, phone }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `signup failed (${res.status})`);
      return;
    }
    setDone(email);
  }

  if (done) {
    return (
      <div>
        <div className="card-head">
          <span className="card-title">✓ Account created</span>
        </div>
        <p style={{ color: "var(--fg)", fontSize: 14, marginBottom: 8 }}>
          Check <strong>{done}</strong> for your temporary password.
        </p>
        <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 20 }}>
          Log in with it, then you&apos;ll be asked to set your own password.
        </p>
        <a href="/login" className="btn-primary" style={{ padding: "10px 16px" }}>
          Go to Sign In →
        </a>
      </div>
    );
  }

  return (
    <form onSubmit={(e) => void submit(e)} style={{ display: "grid", gap: 14 }}>
      <div className="card-head">
        <span className="card-title">Start your free trial</span>
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          Name
        </label>
        <input value={name} onChange={(e) => setName(e.target.value)} required style={{ width: "100%" }} />
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          ✉ Email
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@domain.com"
          required
          style={{ width: "100%" }}
        />
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          📱 Phone / WhatsApp
        </label>
        <PhoneInput onChange={setPhone} required />
        <p style={{ fontSize: 11, color: "var(--dim)", marginTop: 4 }}>
          Used for app alerts only.
        </p>
      </div>

      <button
        type="submit"
        className="btn-primary"
        disabled={busy}
        style={{ justifyContent: "center", padding: 12 }}
      >
        {busy ? "..." : "Start Free Trial →"}
      </button>

      {error ? (
        <p style={{ color: "var(--bad)" }} role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
