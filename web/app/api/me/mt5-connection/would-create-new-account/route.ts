import { proxyToApi } from "@/lib/proxy";

/** POST /api/me/mt5-connection/would-create-new-account -> api POST /api/v1/me/mt5-connection/would-create-new-account */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/me/mt5-connection/would-create-new-account", "POST", req);
}
