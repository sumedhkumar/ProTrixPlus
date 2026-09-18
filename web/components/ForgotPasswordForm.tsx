"use client";

import { useState } from "react";

export function ForgotPasswordForm() {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [email, setEmail] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    await fetch("/api/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }).catch(() => null);
    setBusy(false);
    // Always the same response, whether or not the email exists - no enumeration.
    setDone(true);
  }

  if (done) {
    return (
      <div>
        <div className="card-head">
          <span className="card-title">✓ Check your email</span>
        </div>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>
          If an account exists for <strong>{email}</strong>, a reset link is on its way.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={(e) => void submit(e)} style={{ display: "grid", gap: 14 }}>
      <div className="card-head">
        <span className="card-title">✉ Reset your password</span>
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          Email
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

      <button
        type="submit"
        className="btn-primary"
        disabled={busy}
        style={{ justifyContent: "center", padding: 12 }}
      >
        {busy ? "..." : "Send Reset Link →"}
      </button>
    </form>
  );
}
