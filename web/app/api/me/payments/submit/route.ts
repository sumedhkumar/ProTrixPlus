import { proxyToApi } from "@/lib/proxy";

/** POST /api/me/payments/submit { name, phone, package, utr_reference }
 * -> api POST /api/v1/me/payments/submit (logged-in renewal, tied to the
 * session's own account - email comes from the verified token, not the body). */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/me/payments/submit", "POST", req);
}
