import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";
import { getToken } from "@/lib/auth";

const allowed = [
  { method: "POST", pattern: /^\/api\/v1\/admin\/wallet\/top-ups$/ },
  { method: "PUT", pattern: /^\/api\/v1\/admin\/users\/[0-9a-f-]+\/(controls|subscription|risk-profile|account)$/i },
  { method: "PATCH", pattern: /^\/api\/v1\/admin\/assignments\/[0-9a-f-]+$/i },
  { method: "POST", pattern: /^\/api\/v1\/admin\/marketplace\/manual-activations$/i },
  { method: "POST", pattern: /^\/api\/v1\/admin\/marketplace\/enrollments\/[0-9a-f-]+\/wallet-adjustments$/i },
  { method: "PUT", pattern: /^\/api\/v1\/admin\/marketplace\/(strategies\/[0-9a-f-]+\/offer|enrollments\/[0-9a-f-]+\/mt5-credentials)$/i },
] as const;

export async function POST(request: Request) {
  const input = (await request.json().catch(() => null)) as {
    method?: unknown;
    path?: unknown;
    body?: unknown;
  } | null;
  const method = typeof input?.method === "string" ? input.method.toUpperCase() : "";
  const path = typeof input?.path === "string" ? input.path : "";
  if (!allowed.some((rule) => rule.method === method && rule.pattern.test(path))) {
    return NextResponse.json({ error: "unsupported admin operation" }, { status: 400 });
  }
  const token = getToken();
  if (!token) return NextResponse.json({ error: "not signed in" }, { status: 401 });
  try {
    const result = await apiFetch<unknown>(path, token, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input?.body ?? {}),
    });
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "admin operation failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
