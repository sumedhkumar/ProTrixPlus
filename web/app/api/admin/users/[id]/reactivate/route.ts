import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/users/:id/reactivate -> api POST /api/v1/admin/users/:id/reactivate (api enforces SUPER_ADMIN) */
export async function POST(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/users/${params.id}/reactivate`, "POST", req);
}
