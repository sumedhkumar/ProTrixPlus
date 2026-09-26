import { NextResponse } from "next/server";

import { apiErrorDetail, apiFetch, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { proxyToApi } from "@/lib/proxy";

/** GET /api/admin/alerts -> api GET /api/v1/admin/alerts (read-only, admin only) */
export async function GET() {
  const token = getToken();
  if (!token) return NextResponse.json({ error: "not signed in" }, { status: 401 });
  try {
    const body = await apiFetch("/api/v1/admin/alerts", token);
    return NextResponse.json(body);
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 502;
    return NextResponse.json({ error: "failed", detail: apiErrorDetail(err) }, { status });
  }
}

/** POST /api/admin/alerts -> api POST /api/v1/admin/alerts (api enforces STRATEGY_ADMIN/SUPER_ADMIN) */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/admin/alerts", "POST", req);
}
