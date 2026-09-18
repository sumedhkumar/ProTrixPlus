import { proxyToApi } from "@/lib/proxy";

/** POST /api/set-password { new_password } -> api POST /auth/set-password
 * (forced first-login change, or voluntary). Requires an existing session. */
export async function POST(req: Request) {
  return proxyToApi("/auth/set-password", "POST", req);
}
