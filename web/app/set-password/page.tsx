import { redirect } from "next/navigation";

import { AuthShell } from "@/components/AuthShell";
import { SetPasswordForm } from "@/components/SetPasswordForm";
import { apiFetch, type Identity } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { homePathForRole } from "@/lib/roles";

export default async function SetPasswordPage() {
  const token = getToken();
  if (!token) redirect("/login");

  let identity: Identity;
  try {
    identity = await apiFetch<Identity>("/api/v1/me", token);
  } catch {
    redirect("/login");
  }

  return (
    <AuthShell>
      <div className="auth-center">
        <div className="auth-center-inner">
          <div className="auth-center-header">
            <span className="badge-pill badge-teal">🔒 Set Your Password</span>
            <h1 style={{ fontSize: 28, lineHeight: 1.2, margin: "16px 0 8px" }}>
              Choose a permanent password.
            </h1>
            <p style={{ color: "var(--muted)", fontSize: 14 }}>
              You logged in with a temporary password. Set your own before continuing.
            </p>
          </div>

          <div className="form-panel">
            <SetPasswordForm redirectTo={homePathForRole(identity.role)} />
          </div>
        </div>
      </div>
    </AuthShell>
  );
}
