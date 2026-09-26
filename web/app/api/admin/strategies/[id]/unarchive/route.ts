import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/strategies/:id/unarchive -> api POST /api/v1/admin/strategies/:id/unarchive */
export async function POST(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/strategies/${params.id}/unarchive`, "POST", req);
}
