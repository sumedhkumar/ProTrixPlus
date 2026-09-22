"use client";

import { useState } from "react";

export function ResetPasswordForm({ token }: { token: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setError("passwords do not match");
      return;
    }
    setBusy(true);
    setError(null);
    const res = await fetch("/api/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, new_password: newPassword }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `reset failed (${res.status})`);
      return;
    }
    setDone(true);
  }

  if (!token) {
    return (
      <p style={{ color: "var(--bad)" }} role="alert">
        Missing or invalid reset link. Request a new one from the{" "}
        <a href="/forgot-password">forgot password</a> page.
      </p>
    );
  }

  if (done) {
    return (
      <div>
        <div className="card-head">
          <span className="card-title">✓ Password updated</span>
        </div>
        <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 20 }}>
          You can now sign in with your new password.
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
        <span className="card-title">🔒 New password</span>
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          New password
        </label>
        <input
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          minLength={8}
          required
          style={{ width: "100%" }}
        />
      </div>

      <div>
        <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
          Confirm password
        </label>
        <input
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          minLength={8}
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
        {busy ? "..." : "Reset Password →"}
      </button>

      {error ? (
        <p style={{ color: "var(--bad)" }} role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
