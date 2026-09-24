import { proxyToApi } from "@/lib/proxy";

/** PATCH /api/admin/users/:id/roles -> api PATCH /api/v1/admin/users/:id/roles (api enforces SUPER_ADMIN) */
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/users/${params.id}/roles`, "PATCH", req);
}
