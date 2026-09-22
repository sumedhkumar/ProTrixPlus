import { proxyToApi } from "@/lib/proxy";

/** POST /api/me/mt5-connection/metaapi-link -> api POST /api/v1/me/mt5-connection/metaapi-link */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/me/mt5-connection/metaapi-link", "POST", req);
}
