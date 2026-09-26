import { NextResponse } from "next/server";

import { apiErrorDetail, apiFetch, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";

/** GET /api/admin/alerts/:id/changelog -> api GET .../changelog (read-only, admin only) */
export async function GET(_req: Request, { params }: { params: { id: string } }) {
  const token = getToken();
  if (!token) return NextResponse.json({ error: "not signed in" }, { status: 401 });
  try {
    const body = await apiFetch(`/api/v1/admin/alerts/${params.id}/changelog`, token);
    return NextResponse.json(body);
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 502;
    return NextResponse.json({ error: "failed", detail: apiErrorDetail(err) }, { status });
  }
}
