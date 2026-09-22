import { NextResponse } from "next/server";

import { apiFetch, ApiError } from "@/lib/api";
import { TOKEN_COOKIE } from "@/lib/auth";

interface AuthResponse {
  access_token: string;
  role: "USER" | "SUPER_ADMIN";
  display_name: string;
  subject: string;
  must_change_password: boolean;
}

/** POST /api/auth-session { mode: "signup"|"login", email, password, display_name? }
 * -> real /auth/signup or /auth/login (password-based, not mock). */
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as {
    mode?: unknown;
    email?: unknown;
    password?: unknown;
    display_name?: unknown;
  };
  const mode = body.mode === "signup" ? "signup" : "login";
  const email = typeof body.email === "string" ? body.email : "";
  const password = typeof body.password === "string" ? body.password : "";
  const displayName = typeof body.display_name === "string" ? body.display_name : "";

  const payload =
    mode === "signup" ? { email, password, display_name: displayName } : { email, password };

  let auth: AuthResponse;
  try {
    auth = await apiFetch<AuthResponse>(`/auth/${mode}`, undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 502;
    return NextResponse.json({ error: `${mode} failed`, detail: String(err) }, { status });
  }

  const res = NextResponse.json({
    subject: auth.subject,
    role: auth.role,
    display_name: auth.display_name,
    must_change_password: auth.must_change_password,
  });
  res.cookies.set(TOKEN_COOKIE, auth.access_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60,
  });
  return res;
}
