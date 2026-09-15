"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const DEV_USERS = [
  { email: "alice@example.test", label: "Alice Trader" },
  { email: "bob@example.test", label: "Bob Trader" },
] as const;

export default function LoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function signInUser(email: string) {
    setBusy(email);
    setError(null);
    const res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "USER", email }),
    });
    if (!res.ok) {
      setBusy(null);
      setError(`sign-in failed (${res.status})`);
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  async function signInAdmin() {
    setBusy("SUPER_ADMIN");
    setError(null);
    const res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "SUPER_ADMIN" }),
    });
    if (!res.ok) {
      setBusy(null);
      setError(`sign-in failed (${res.status})`);
      return;
    }
    router.push("/admin");
    router.refresh();
  }

  return (
    <div className="container">
      <div className="panel" style={{ maxWidth: 460 }}>
        <h1>Protrixplus dev sign-in</h1>
        <p style={{ color: "var(--muted)" }}>
          Local development identity only. No passwords or OIDC are enabled.
          Choose the ProTrixplus user whose dashboard you want to view.
        </p>
        <div style={{ display: "flex", gap: 12, marginTop: 16, flexWrap: "wrap" }}>
          {DEV_USERS.map((user) => (
            <button
              key={user.email}
              onClick={() => void signInUser(user.email)}
              disabled={busy !== null}
            >
              {busy === user.email ? "..." : `Sign in as ${user.label}`}
            </button>
          ))}
          <button
            className="secondary"
            onClick={() => void signInAdmin()}
            disabled={busy !== null}
          >
            {busy === "SUPER_ADMIN" ? "..." : "Sign in as SUPER_ADMIN"}
          </button>
        </div>
        {error ? (
          <p style={{ color: "var(--bad)", marginTop: 12 }} role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
