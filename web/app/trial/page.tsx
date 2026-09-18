import Link from "next/link";

import { TrialSignupForm } from "@/components/TrialSignupForm";

const TRIAL_POINTS = [
  {
    icon: "🎁",
    color: "teal" as const,
    title: "No Password to Set Up Front",
    desc: "Just your name, email, and phone. We email you a temporary password to sign in with.",
  },
  {
    icon: "🔒",
    color: "purple" as const,
    title: "Set Your Own Password on First Login",
    desc: "You choose a permanent password the first time you sign in - nothing stored in your inbox afterward.",
  },
  {
    icon: "⏱",
    color: "purple" as const,
    title: "Full 7 Days, No Card Required",
    desc: "Complete dashboard access and live execution tracking for the entire trial window.",
  },
];

export default function TrialPage() {
  return (
    <div className="login-split">
      <div>
        <span className="badge-pill badge-teal">🛡 Free 7-Day Trial</span>
        <h1 style={{ fontSize: 36, lineHeight: 1.15, margin: "16px 0" }}>
          Try ProTrixPlus free for 7 days.
        </h1>
        <p style={{ color: "var(--muted)", fontSize: 15, marginBottom: 28, maxWidth: 440 }}>
          No password to create, no card required. We&apos;ll email you a temporary password -
          you&apos;ll set your own the first time you log in.
        </p>

        <div style={{ display: "grid", gap: 12, marginBottom: 24 }}>
          {TRIAL_POINTS.map((f) => (
            <div key={f.title} className="card" style={{ display: "flex", gap: 14, padding: 16 }}>
              <div className={`icon-badge ${f.color}`}>{f.icon}</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{f.title}</div>
                <div style={{ color: "var(--muted)", fontSize: 13 }}>{f.desc}</div>
              </div>
            </div>
          ))}
        </div>

        <Link href="/login" style={{ fontSize: 13, textDecoration: "none" }}>
          Already have an account? Sign in →
        </Link>
      </div>

      <div className="card" style={{ padding: 28 }}>
        <TrialSignupForm />
      </div>
    </div>
  );
}
