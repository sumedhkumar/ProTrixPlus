import { proxyToApi } from "@/lib/proxy";

/** POST /api/me/assignments/subscribe -> api POST /api/v1/me/assignments/subscribe */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/me/assignments/subscribe", "POST", req);
}
