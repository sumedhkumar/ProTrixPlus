"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function SetPasswordForm({ redirectTo }: { redirectTo: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    const res = await fetch("/api/set-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: newPassword }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `failed (${res.status})`);
      return;
    }
    router.push(redirectTo);
    router.refresh();
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
        {busy ? "..." : "Set Password →"}
      </button>

      {error ? (
        <p style={{ color: "var(--bad)" }} role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
