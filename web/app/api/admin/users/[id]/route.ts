import { proxyToApi } from "@/lib/proxy";

/** DELETE /api/admin/users/:id -> api DELETE /api/v1/admin/users/:id (api enforces SUPER_ADMIN) */
export async function DELETE(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/users/${params.id}`, "DELETE", req);
}
