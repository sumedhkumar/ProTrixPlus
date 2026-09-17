import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";
import { getToken } from "@/lib/auth";

const allowed = [
  /^\/api\/v1\/marketplace\/strategies\/[0-9a-f-]+\/checkout$/i,
  /^\/api\/v1\/marketplace\/enrollments\/[0-9a-f-]+\/(top-ups|mt5-credentials)$/i,
  /^\/api\/v1\/payments\/razorpay\/verify$/i,
] as const;

export async function POST(request: Request) {
  const input = (await request.json().catch(() => null)) as {
    path?: unknown;
    body?: unknown;
    idempotencyKey?: unknown;
  } | null;
  const path = typeof input?.path === "string" ? input.path : "";
  if (!allowed.some((pattern) => pattern.test(path))) {
    return NextResponse.json({ error: "unsupported marketplace operation" }, { status: 400 });
  }
  const token = getToken();
  if (!token) return NextResponse.json({ error: "not signed in" }, { status: 401 });
  try {
    const result = await apiFetch<unknown>(path, token, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(typeof input?.idempotencyKey === "string" ? { "Idempotency-Key": input.idempotencyKey } : {}),
      },
      body: JSON.stringify(input?.body ?? {}),
    });
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "marketplace operation failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
