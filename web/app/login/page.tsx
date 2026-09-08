"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Role = "USER" | "SUPER_ADMIN";

export default function LoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState<Role | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function signIn(role: Role) {
    setBusy(role);
    setError(null);
    const res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!res.ok) {
      setBusy(null);
      setError(`sign-in failed (${res.status})`);
      return;
    }
    router.push(role === "SUPER_ADMIN" ? "/admin" : "/dashboard");
    router.refresh();
  }

  return (
    <div className="container">
      <div className="panel" style={{ maxWidth: 460 }}>
        <h1>Protrixplus dev sign-in</h1>
        <p style={{ color: "var(--muted)" }}>
          Mock identity only. No passwords, no OIDC. Pick a fake role.
        </p>
        <div style={{ display: "flex", gap: 12, marginTop: 16 }}>
          <button onClick={() => void signIn("USER")} disabled={busy !== null}>
            {busy === "USER" ? "..." : "Sign in as USER"}
          </button>
          <button
            className="secondary"
            onClick={() => void signIn("SUPER_ADMIN")}
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
