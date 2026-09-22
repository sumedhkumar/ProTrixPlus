import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/payment-submissions/:id/approve
 * -> api POST /api/v1/admin/payment-submissions/:id/approve */
export async function POST(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/payment-submissions/${params.id}/approve`, "POST", req);
}
