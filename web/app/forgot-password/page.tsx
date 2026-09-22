import Link from "next/link";

import { AuthShell } from "@/components/AuthShell";
import { ForgotPasswordForm } from "@/components/ForgotPasswordForm";

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      right={
        <Link href="/login" className="btn-ghost" style={{ padding: "8px 16px" }}>
          Sign In →
        </Link>
      }
    >
      <div className="auth-center">
        <div className="auth-center-inner">
          <div className="auth-center-header">
            <span className="badge-pill badge-teal">🔑 Password Reset</span>
            <h1 style={{ fontSize: 28, lineHeight: 1.2, margin: "16px 0 8px" }}>
              Forgot your password?
            </h1>
            <p style={{ color: "var(--muted)", fontSize: 14 }}>
              Enter the email on your account and we&apos;ll send you a link to reset it.
            </p>
          </div>

          <div className="form-panel">
            <ForgotPasswordForm />
          </div>
        </div>
      </div>
    </AuthShell>
  );
}
