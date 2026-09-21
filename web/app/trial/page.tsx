import Link from "next/link";

import { AuthShell } from "@/components/AuthShell";
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
    <AuthShell
      right={
        <Link href="/login" className="btn-ghost" style={{ padding: "8px 16px" }}>
          Sign In →
        </Link>
      }
    >
    <div className="login-split">
      <div>
        <span className="badge-pill badge-teal">🛡 Free 7-Day Trial</span>
        <h1 className="hero-heading">Try ProTrixPlus free for 7 days.</h1>
        <p className="hero-copy">
          No password to create, no card required. We&apos;ll email you a temporary password -
          you&apos;ll set your own the first time you log in.
        </p>

        <div className="feature-list">
          {TRIAL_POINTS.map((f) => (
            <div key={f.title} className="feature-row">
              <div className={`feature-icon ${f.color}`}>{f.icon}</div>
              <div>
                <div className="feature-row-title">{f.title}</div>
                <div className="feature-row-desc">{f.desc}</div>
              </div>
            </div>
          ))}
        </div>

        <Link href="/login" style={{ fontSize: 13, textDecoration: "none" }}>
          Already have an account? Sign in →
        </Link>
      </div>

      <div className="form-panel">
        <TrialSignupForm />
      </div>
    </div>
    </AuthShell>
  );
}
