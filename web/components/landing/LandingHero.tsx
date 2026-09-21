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

const HOW_IT_WORKS: [string, string, string][] = [
  ["1", "Start your free trial", "Sign up with your name, email, and phone - no password to set up front."],
  ["2", "Get your login by email", "We email you a temporary password to sign in with."],
  ["3", "Set your own password", "First login asks you to choose a permanent password."],
  ["4", "Trade with confidence", "Your dashboard shows live execution status and your subscription countdown."],
];

export function LandingHero() {
  return (
    <section className="landing-hero">
      <div>
        <span className="badge-pill badge-teal">🛡 AI-Evolved Strategy Automation</span>
        <h1 className="hero-heading" style={{ fontSize: 42 }}>
          Automated MT5 Execution for Modern Quant Traders.
        </h1>
        <p className="hero-copy" style={{ marginBottom: 28 }}>
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

        <div className="feature-list" style={{ marginBottom: 0 }}>
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
      </div>

      <div className="form-panel">
        <div className="panel-heading">How it works</div>
        <div className="steps-list">
          {HOW_IT_WORKS.map(([n, title, desc], i) => (
            <div key={n} className="step-row">
              <div className="step-rail">
                <span className="step-num">{n}</span>
                {i < HOW_IT_WORKS.length - 1 ? <span className="step-line" /> : null}
              </div>
              <div>
                <div className="step-title">{title}</div>
                <div className="step-desc">{desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
