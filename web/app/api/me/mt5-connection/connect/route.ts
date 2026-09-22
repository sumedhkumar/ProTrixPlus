import { proxyToApi } from "@/lib/proxy";

/** POST /api/me/mt5-connection/connect -> api POST /api/v1/me/mt5-connection/connect */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/me/mt5-connection/connect", "POST", req);
}
