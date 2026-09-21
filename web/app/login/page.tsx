"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthShell } from "@/components/AuthShell";

type Role = "USER" | "SUPER_ADMIN";
type AuthMode = "login" | "signup";

const DEMO_PASSWORD = "Demo12345!";
const DEMO_PROFILES: { name: string; email: string; role: "ADMIN" | "CLIENT" }[] = [
  { name: "Alex Vance", email: "alex.vance@protrixplus.test", role: "ADMIN" },
  { name: "Marcus Sterling", email: "marcus.sterling@apexcapital.co", role: "CLIENT" },
  { name: "Elena Rostova", email: "elena.rostova@quantfund.net", role: "CLIENT" },
];

const FEATURES = [
  {
    icon: "🖥",
    color: "teal" as const,
    title: "Dual Login Security (Email or Mobile)",
    desc: "Fast sign-in via email address with password-based authentication.",
  },
  {
    icon: "📡",
    color: "purple" as const,
    title: "Idempotent Webhook Gateway",
    desc: "Signal deduplication (signal_id / idempotency_key) blocks duplicate signal execution - this one is real, not marketing copy.",
  },
  {
    icon: "🔑",
    color: "purple" as const,
    title: "Investor-Grade Security",
    desc: "MT5 credentials are never stored as plaintext passwords here - real broker connectivity is pending MetaApi.cloud credentials.",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");

  async function doAuth(mode: AuthMode, authEmail: string, authPassword: string, name?: string) {
    setBusy(mode);
    setError(null);
    const res = await fetch("/api/auth-session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, email: authEmail, password: authPassword, display_name: name }),
    });
    if (!res.ok) {
      setBusy(null);
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `${mode} failed (${res.status})`);
      return;
    }
    const body = (await res.json()) as { role: Role; must_change_password: boolean };
    if (body.must_change_password) {
      router.push("/set-password");
    } else {
      router.push(body.role === "SUPER_ADMIN" ? "/admin" : "/dashboard");
    }
    router.refresh();
  }

  async function signInMock(role: Role) {
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

  function fillDemoProfile(p: (typeof DEMO_PROFILES)[number]) {
    setAuthMode("login");
    setEmail(p.email);
    setPassword(DEMO_PASSWORD);
    void doAuth("login", p.email, DEMO_PASSWORD);
  }

  return (
    <AuthShell
      right={
        <Link href="/trial" style={{ fontSize: 13, fontWeight: 600, textDecoration: "none" }}>
          Start Free Trial →
        </Link>
      }
    >
    <div className="login-split">
      <div>
        <span className="badge-pill badge-teal">🛡 Multi-User Fan-Out Architecture</span>
        <h1 className="hero-heading">Automated MT5 Execution for Modern Quant Traders.</h1>
        <p className="hero-copy">
          Connect TradingView alerts to multiple client MT5 accounts, with per-client lot-size
          entitlement and admin-controlled strategy access.
        </p>

        <div className="feature-list">
          {FEATURES.map((f) => (
            <div key={f.title} className="feature-row">
              <div className={`feature-icon ${f.color}`}>{f.icon}</div>
              <div>
                <div className="feature-row-title">{f.title}</div>
                <div className="feature-row-desc">{f.desc}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="inline-divider">
          <span className="inline-divider-label">✨ 1-Click Demo Profiles - real accounts, instant sign-in</span>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {DEMO_PROFILES.map((p) => (
              <button
                key={p.email}
                type="button"
                className="demo-profile-btn"
                disabled={busy !== null}
                onClick={() => fillDemoProfile(p)}
              >
                <span className="dot green" /> {busy === "login" ? "..." : p.name}{" "}
                <span className="role-tag">({p.role})</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="form-panel">
        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          <button
            type="button"
            className={`auth-tab ${authMode === "login" ? "active" : ""}`}
            onClick={() => setAuthMode("login")}
          >
            🔒 Sign In
          </button>
          <button
            type="button"
            className={`auth-tab ${authMode === "signup" ? "active" : ""}`}
            onClick={() => setAuthMode("signup")}
          >
            👤 Create Account
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void doAuth(authMode, email, password, displayName);
          }}
          style={{ display: "grid", gap: 14 }}
        >
          {authMode === "signup" ? (
            <div>
              <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
                Display name
              </label>
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
                style={{ width: "100%" }}
              />
            </div>
          ) : null}

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
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <label style={{ fontSize: 12, color: "var(--muted)" }}>🔒 Password</label>
              <Link
                href="/forgot-password"
                style={{ fontSize: 12, color: "var(--accent)", textDecoration: "none" }}
              >
                Forgot password?
              </Link>
            </div>
            <div style={{ position: "relative" }}>
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                required
                style={{ width: "100%", paddingRight: 40 }}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                style={{
                  position: "absolute",
                  right: 4,
                  top: 4,
                  background: "none",
                  color: "var(--dim)",
                  padding: 6,
                }}
              >
                {showPassword ? "🙈" : "👁"}
              </button>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--muted)" }}>
              <input type="checkbox" defaultChecked style={{ width: "auto" }} />
              Keep me signed in
            </label>
            <span className="badge-pill badge-green">🛡 256-bit TLS</span>
          </div>

          <button type="submit" className="btn-primary" disabled={busy !== null} style={{ justifyContent: "center", padding: 12 }}>
            {busy === authMode
              ? "..."
              : authMode === "signup"
                ? "Create Account →"
                : "Sign In to Terminal →"}
          </button>
        </form>

        {error ? (
          <p style={{ color: "var(--bad)", marginTop: 12 }} role="alert">
            {error}
          </p>
        ) : null}

        {authMode === "signup" ? (
          <p style={{ color: "var(--dim)", fontSize: 12, marginTop: 12 }}>
            Want a free 7-day trial instead?{" "}
            <Link href="/trial" style={{ color: "var(--accent)", textDecoration: "none" }}>
              Start here →
            </Link>
          </p>
        ) : null}

        <hr style={{ margin: "20px 0", borderColor: "var(--panel-border)" }} />
        <p style={{ color: "var(--dim)", fontSize: 12, marginBottom: 8 }}>
          Dev/testing only - mock identity, no password:
        </p>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="secondary" onClick={() => void signInMock("USER")} disabled={busy !== null}>
            Mock USER
          </button>
          <button className="secondary" onClick={() => void signInMock("SUPER_ADMIN")} disabled={busy !== null}>
            Mock SUPER_ADMIN
          </button>
        </div>
      </div>
    </div>
    </AuthShell>
  );
}
