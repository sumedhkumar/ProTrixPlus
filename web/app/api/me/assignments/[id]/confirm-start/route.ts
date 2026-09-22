import { proxyToApi } from "@/lib/proxy";

/** POST /api/me/assignments/:id/confirm-start -> api POST /api/v1/me/assignments/:id/confirm-start */
export async function POST(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/me/assignments/${params.id}/confirm-start`, "POST", req);
}
