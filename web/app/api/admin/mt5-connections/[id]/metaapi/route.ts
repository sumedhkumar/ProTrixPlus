import { proxyToApi } from "@/lib/proxy";

/** PATCH /api/admin/mt5-connections/:id/metaapi -> api PATCH /api/v1/admin/mt5-connections/:id/metaapi */
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/mt5-connections/${params.id}/metaapi`, "PATCH", req);
}
