import { proxyToApi } from "@/lib/proxy";

/** PATCH /api/admin/strategies/:id/alerts -> api PATCH /api/v1/admin/strategies/:id/alerts */
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/strategies/${params.id}/alerts`, "PATCH", req);
}
