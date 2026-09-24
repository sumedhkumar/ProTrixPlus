import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/users/:id/deactivate -> api POST /api/v1/admin/users/:id/deactivate (api enforces SUPER_ADMIN) */
export async function POST(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/users/${params.id}/deactivate`, "POST", req);
}
