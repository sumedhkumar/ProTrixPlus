import { NextResponse } from "next/server";

import { apiErrorDetail, apiFetch, ApiError } from "@/lib/api";

/** POST /api/forgot-password { email } -> api POST /auth/forgot-password.
 * Public. Always a generic response - no email enumeration. */
export async function POST(req: Request) {
  const body = await req.text();
  try {
    const result = await apiFetch<{ detail: string }>("/auth/forgot-password", undefined, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    return NextResponse.json(result);
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 502;
    return NextResponse.json({ error: "request failed", detail: apiErrorDetail(err) }, { status });
  }
}
