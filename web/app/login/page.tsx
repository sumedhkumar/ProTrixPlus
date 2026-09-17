"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Brand, Icon } from "@/components/Icon";

const DEV_USERS = [
  { email: "alice@example.test", label: "Alice Trader", initials: "AT" },
  { email: "bob@example.test", label: "Bob Trader", initials: "BT" },
] as const;

export default function LoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function signIn(role: "USER" | "SUPER_ADMIN", email?: string) {
    setBusy(email ?? role);
    setError(null);
    try {
      const res = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, ...(email ? { email } : {}) }),
      });
      if (!res.ok) throw new Error(`Sign-in failed (${res.status}). Please try again.`);
      router.push(role === "SUPER_ADMIN" ? "/admin" : "/dashboard");
      router.refresh();
    } catch (cause) {
      setBusy(null);
      setError(cause instanceof Error ? cause.message : "Unable to sign in. Please try again.");
    }
  }

  return (
    <div className="login-page">
      <section className="login-story" aria-label="About ProTrixPlus">
        <Link href="/marketplace" className="brand-link" aria-label="ProTrixPlus marketplace"><Brand /></Link>
        <div className="login-story-content">

          <h2>Your strategy.<br /><span>In motion.</span></h2>
          <p>Bring your signals, strategies, and trading accounts together in one focused workspace.</p>
          <div className="login-flow" aria-label="TradingView signals flow through ProTrixPlus controls to MT5 execution">
            <div><Icon name="signal" size={24} /><strong>TradingView</strong><small>Your signals</small></div><Icon name="arrow" size={18} />
            <div><Icon name="shield" size={24} /><strong>ProTrixPlus</strong><small>Your controls</small></div><Icon name="arrow" size={18} />
            <div><Icon name="server" size={24} /><strong>MetaTrader 5</strong><small>Your execution</small></div>
          </div>
        </div>
        <div className="login-story-footer"><Icon name="layers" size={16} /> Dedicated accounts. Strategy-level control.</div>
      </section>
      <main className="login-main" id="main-content">
        <div className="login-card">
          <div className="login-lock"><Icon name="lock" size={23} /></div>

          <h1>Make your next move.</h1>
          <p className="login-intro">Sign in to manage your strategies, check your accounts, and follow every execution.</p>
          <button className="auth0-button" onClick={() => { window.location.href = "/api/auth/login"; }} disabled={busy !== null}>Sign in or create an account <Icon name="arrow" size={18} /></button>
          <p className="login-auth-note"><Icon name="lock" size={12} /> Secure sign-in with Auth0 when configured.</p>
          <div className="login-divider">Local development accounts</div>
          <div className="dev-user-grid">
            {DEV_USERS.map((user) => (
              <button className="secondary dev-user-button" key={user.email} onClick={() => void signIn("USER", user.email)} disabled={busy !== null}>
                <span className="identity-avatar" aria-hidden="true">{user.initials}</span>
                <span>{busy === user.email ? "Signing in…" : `Sign in as ${user.label}`}</span>
              </button>
            ))}
          </div>
          <button className="secondary admin-signin" onClick={() => void signIn("SUPER_ADMIN")} disabled={busy !== null}><Icon name="shield" size={16} />{busy === "SUPER_ADMIN" ? "Signing in…" : "Sign in as SUPER_ADMIN"}</button>
          {error ? <p className="login-error" role="alert">{error}</p> : null}
          <p className="login-footer"><Link href="/marketplace">Explore the marketplace <Icon name="arrow" size={15} /></Link></p>
        </div>
      </main>
    </div>
  );
}
