import { proxyToApi } from "@/lib/proxy";

/** PATCH /api/me/assignments/:id/multiplier { multiplier } -> api PATCH .../multiplier */
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/me/assignments/${params.id}/multiplier`, "PATCH", req);
}
