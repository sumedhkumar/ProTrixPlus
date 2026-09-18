import Link from "next/link";

const FEATURES = [
  {
    icon: "🖥",
    color: "teal" as const,
    title: "TradingView to MT5, Automatically",
    desc: "Connect a TradingView strategy alert straight through to your MetaTrader 5 account - no manual order entry.",
  },
  {
    icon: "📡",
    color: "purple" as const,
    title: "Idempotent Signal Delivery",
    desc: "Every signal is deduplicated end to end, so a repeated or retried alert never fires a duplicate trade.",
  },
  {
    icon: "🔑",
    color: "purple" as const,
    title: "Per-Client Entitlement Control",
    desc: "Each strategy, lot size, and access window is admin-controlled and tracked per client account.",
  },
];

export function LandingHero() {
  return (
    <section className="landing-hero">
      <div>
        <span className="badge-pill badge-teal">🛡 AI-Evolved Strategy Automation</span>
        <h1 style={{ fontSize: 42, lineHeight: 1.15, margin: "16px 0" }}>
          Automated MT5 Execution for Modern Quant Traders.
        </h1>
        <p style={{ color: "var(--muted)", fontSize: 15, marginBottom: 28, maxWidth: 480 }}>
          ProTrixPlus routes TradingView signals to your MetaTrader 5 account with per-client
          lot-size entitlement, execution tracking, and admin oversight - start with a free 7-day
          trial, no card required.
        </p>

        <div style={{ display: "flex", gap: 12, marginBottom: 32, flexWrap: "wrap" }}>
          <Link href="/trial" className="btn-primary" style={{ padding: "12px 20px" }}>
            Start Free 7-Day Trial →
          </Link>
          <Link
            href="/login"
            style={{
              padding: "12px 20px",
              borderRadius: 8,
              border: "1px solid var(--border)",
              color: "var(--fg)",
              fontWeight: 600,
              fontSize: 14,
              textDecoration: "none",
            }}
          >
            Sign In
          </Link>
        </div>

        <div style={{ display: "grid", gap: 12 }}>
          {FEATURES.map((f) => (
            <div key={f.title} className="card" style={{ display: "flex", gap: 14, padding: 16 }}>
              <div className={`icon-badge ${f.color}`}>{f.icon}</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{f.title}</div>
                <div style={{ color: "var(--muted)", fontSize: 13 }}>{f.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ padding: 24 }}>
        <div className="card-head">
          <span className="card-title">How it works</span>
        </div>
        <div style={{ display: "grid", gap: 18 }}>
          {[
            ["1", "Start your free trial", "Sign up with your name, email, and phone - no password to set up front."],
            ["2", "Get your login by email", "We email you a temporary password to sign in with."],
            ["3", "Set your own password", "First login asks you to choose a permanent password."],
            ["4", "Trade with confidence", "Your dashboard shows live execution status and your subscription countdown."],
          ].map(([n, title, desc]) => (
            <div key={n} style={{ display: "flex", gap: 14 }}>
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  background: "var(--teal-dim)",
                  color: "var(--teal)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 800,
                  fontSize: 13,
                  flex: "none",
                }}
              >
                {n}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{title}</div>
                <div style={{ color: "var(--muted)", fontSize: 13 }}>{desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
