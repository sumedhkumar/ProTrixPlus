import { proxyToApi } from "@/lib/proxy";

/** PATCH /api/admin/assignments/:id -> api PATCH /api/v1/admin/assignments/:id (override/revoke) */
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/assignments/${params.id}`, "PATCH", req);
}
