import { proxyToApi } from "@/lib/proxy";

/** POST /api/me/mt5-setup-fee/pay -> api POST /api/v1/me/mt5-setup-fee/pay */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/me/mt5-setup-fee/pay", "POST", req);
}
