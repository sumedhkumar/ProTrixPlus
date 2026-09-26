import { NextResponse } from "next/server";

import { apiErrorDetail, apiFetch, ApiError } from "@/lib/api";

/** POST /api/reset-password { token, new_password } -> api POST /auth/reset-password. Public. */
export async function POST(req: Request) {
  const body = await req.text();
  try {
    const result = await apiFetch<{ ok: boolean }>("/auth/reset-password", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    return NextResponse.json(result);
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 502;
    return NextResponse.json({ error: "reset failed", detail: apiErrorDetail(err) }, { status });
  }
}
