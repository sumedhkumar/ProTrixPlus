import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/strategies -> api POST /api/v1/admin/strategies (api enforces STRATEGY_ADMIN/SUPER_ADMIN) */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/admin/strategies", "POST", req);
}
