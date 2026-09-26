import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/strategies/:id/archive -> api POST /api/v1/admin/strategies/:id/archive */
export async function POST(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/strategies/${params.id}/archive`, "POST", req);
}
