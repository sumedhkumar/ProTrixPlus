import { NextResponse } from "next/server";

import { apiFetch, ApiError } from "@/lib/api";

/** POST /api/google-signup { credential } -> api POST /auth/signup-google
 * (Google-verified email, password-less - same temp-password email as
 * /api/trial-signup). Public, no session yet. */
export async function POST(req: Request) {
  const body = await req.text();
  try {
    const result = await apiFetch<{ email: string; message: string }>(
      "/auth/signup-google",
      undefined,
      { method: "POST", headers: { "Content-Type": "application/json" }, body },
    );
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 502;
    return NextResponse.json({ error: "signup failed", detail: String(err) }, { status });
  }
}
