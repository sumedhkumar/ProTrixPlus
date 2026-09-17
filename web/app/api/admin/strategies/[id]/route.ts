import { proxyToApi } from "@/lib/proxy";

/** PATCH /api/admin/strategies/:id -> api PATCH /api/v1/admin/strategies/:id */
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/strategies/${params.id}`, "PATCH", req);
}
