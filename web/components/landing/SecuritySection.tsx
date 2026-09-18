// Only claims that are actually true of this codebase today - no fabricated
// certifications or customer counts. See api/app/auth.py, api/app/vault/,
// and the idempotency guarantees in contracts/db models' unique constraints.
const TRUST_POINTS = [
  {
    icon: "🔐",
    title: "Passwords Never Stored in Plaintext",
    desc: "PBKDF2-HMAC-SHA256, 600,000 iterations, salted per account - the OWASP-recommended standard.",
  },
  {
    icon: "🔁",
    title: "Idempotent by Design",
    desc: "Every signal is deduplicated end to end (signal_id + idempotency_key) - a retried alert can never fire a duplicate trade.",
  },
  {
    icon: "🗝",
    title: "MT5 Credentials, Never Plaintext",
    desc: "Broker credentials are held behind short-lived, scoped handles - never returned to the browser or written to logs.",
  },
  {
    icon: "🧾",
    title: "Every Execution Is Tracked",
    desc: "Signal-to-fill status (received, dispatched, acknowledged, filled) is recorded per client for full auditability.",
  },
];

export function SecuritySection() {
  return (
    <section className="landing-section" id="security">
      <div className="landing-section-head">
        <h2>Built With Security in Mind</h2>
        <p>
          No payment gateway or broker integration is live yet, but the parts that are - auth,
          execution tracking, credential handling - are built to the same standard from day one.
        </p>
      </div>

      <div className="stat-grid">
        {TRUST_POINTS.map((p) => (
          <div key={p.title} className="card" style={{ display: "flex", gap: 14, padding: 16 }}>
            <div className="icon-badge teal" style={{ fontSize: 20 }}>
              {p.icon}
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13.5, marginBottom: 4 }}>{p.title}</div>
              <div style={{ color: "var(--muted)", fontSize: 12.5 }}>{p.desc}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
