import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/payment-submissions/:id/reject { reason? }
 * -> api POST /api/v1/admin/payment-submissions/:id/reject */
export async function POST(req: Request, { params }: { params: { id: string } }) {
  return proxyToApi(`/api/v1/admin/payment-submissions/${params.id}/reject`, "POST", req);
}
