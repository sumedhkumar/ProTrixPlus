import { proxyToApi } from "@/lib/proxy";

/** POST /api/me/mt5-connection/check -> api POST /api/v1/me/mt5-connection/check */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/me/mt5-connection/check", "POST", req);
}
