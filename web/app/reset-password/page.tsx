import { ResetPasswordForm } from "@/components/ResetPasswordForm";

export default function ResetPasswordPage({
  searchParams,
}: {
  searchParams: { token?: string };
}) {
  return (
    <div className="auth-center">
      <div className="auth-center-inner">
        <div className="auth-center-header">
          <span className="badge-pill badge-teal">🔑 Password Reset</span>
          <h1 style={{ fontSize: 28, lineHeight: 1.2, margin: "16px 0 0" }}>
            Choose a new password.
          </h1>
        </div>

        <div className="card" style={{ padding: 28 }}>
          <ResetPasswordForm token={searchParams.token ?? ""} />
        </div>
      </div>
    </div>
  );
}
