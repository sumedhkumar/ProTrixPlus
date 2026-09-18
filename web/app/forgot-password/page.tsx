import { ForgotPasswordForm } from "@/components/ForgotPasswordForm";

export default function ForgotPasswordPage() {
  return (
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

        <div className="card" style={{ padding: 28 }}>
          <ForgotPasswordForm />
        </div>
      </div>
    </div>
  );
}
