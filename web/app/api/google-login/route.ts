import { NextResponse } from "next/server";

import { apiErrorDetail, apiFetch, ApiError } from "@/lib/api";
import { TOKEN_COOKIE } from "@/lib/auth";
import type { Role } from "@/lib/roles";

interface AuthResponse {
  access_token: string;
  role: Role;
  display_name: string;
  subject: string;
  must_change_password: boolean;
}

/** POST /api/google-login { credential } -> api POST /auth/login-google.
 * Only succeeds once the account's mandatory first password login has
 * cleared must_change_password (see auth.py login_google). */
export async function POST(req: Request) {
  const body = await req.text();

  let auth: AuthResponse;
  try {
    auth = await apiFetch<AuthResponse>("/auth/login-google", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 502;
    return NextResponse.json({ error: "login failed", detail: apiErrorDetail(err) }, { status });
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
