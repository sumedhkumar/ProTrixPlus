import { NextResponse } from "next/server";

import { apiFetch, ApiError } from "@/lib/api";

/** POST /api/payments/submit { name, email, phone, package, utr_reference }
 * -> api POST /api/v1/payments/submit. Public - anonymous applicant, no
 * account yet. For a logged-in renewal, see /api/me/payments/submit instead. */
export async function POST(req: Request) {
  const body = await req.text();
  try {
    const result = await apiFetch<{ id: string; status: string }>(
      "/api/v1/payments/submit",
      undefined,
      { method: "POST", headers: { "Content-Type": "application/json" }, body },
    );
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 502;
    return NextResponse.json({ error: "submission failed", detail: String(err) }, { status });
  }
}
