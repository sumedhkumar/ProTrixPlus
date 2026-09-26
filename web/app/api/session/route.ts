import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";
import { TOKEN_COOKIE } from "@/lib/auth";
import { isRole, type Role } from "@/lib/roles";

interface DevLoginResponse {
  access_token: string;
  role: Role;
  display_name: string;
  subject: string;
}

/** POST /api/session { role } -> sets the dev identity cookie via api /dev/login. */
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { role?: unknown; subject?: unknown };
  const role = isRole(body.role) ? body.role : "USER";

  let login: DevLoginResponse;
  try {
    login = await apiFetch<DevLoginResponse>("/dev/login", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role,
        subject: typeof body.subject === "string" ? body.subject : null,
      }),
    });
  } catch (err) {
    return NextResponse.json(
      { error: "dev login failed", detail: String(err) },
      { status: 502 },
    );
  }

  const res = NextResponse.json({
    subject: login.subject,
    role: login.role,
    display_name: login.display_name,
  });
  res.cookies.set(TOKEN_COOKIE, login.access_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60,
  });
  return res;
}

/** DELETE /api/session -> sign out. */
export function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(TOKEN_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
