import { proxyToApi } from "@/lib/proxy";

/** POST /api/admin/invites -> api POST /api/v1/admin/invites (api enforces SUPER_ADMIN) */
export async function POST(req: Request) {
  return proxyToApi("/api/v1/admin/invites", "POST", req);
}
