import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/assignments -> api POST /api/v1/admin/assignments (grant entitlement) */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/admin/assignments", "POST", req);
}
