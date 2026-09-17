import { proxyToApi } from "@/lib/proxy";

/** POST /api/me/assignments/preview-lot -> api POST .../preview-lot (stateless lot-size math, real formula) */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/me/assignments/preview-lot", "POST", req);
}
