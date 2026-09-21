import { proxyToApi } from "@/lib/proxy";

/** PATCH /api/admin/alerts/:id -> api PATCH /api/v1/admin/alerts/:id */
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/alerts/${params.id}`, "PATCH", req);
}
