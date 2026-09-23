import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/assignments/:id/approve -> api POST /api/v1/admin/assignments/:id/approve */
export async function POST(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/assignments/${params.id}/approve`, "POST", req);
}
