import type { ReactNode } from "react";

import { authFont } from "@/lib/fonts";

import { BrandMark } from "./BrandMark";

/**
 * Shared chrome for every pre-signin page (landing excluded - it has its own
 * full nav). Gives /login, /trial, /subscribe, /forgot-password,
 * /reset-password, /set-password a consistent brand header, background, and
 * font - none of which touches the post-login dashboard/admin shell.
 */
export function AuthShell({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className={`auth-shell ${authFont.variable}`}>
      <div className="auth-shell-glow" aria-hidden />
      <header className="auth-shell-header">
        <BrandMark size="sm" />
        {right}
      </header>
      <main className="auth-shell-main">{children}</main>
    </div>
  );
}
