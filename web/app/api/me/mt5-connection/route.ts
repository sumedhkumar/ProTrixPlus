import { proxyToApi } from "@/lib/proxy";

/** PUT /api/me/mt5-connection { broker_server, login } -> api PUT /api/v1/me/mt5-connection */
export async function PUT(req: Request) {
  return proxyToApi("/api/v1/me/mt5-connection", "PUT", req);
}

/** DELETE /api/me/mt5-connection -> api DELETE /api/v1/me/mt5-connection (real disconnect) */
export async function DELETE(req: Request) {
  return proxyToApi("/api/v1/me/mt5-connection", "DELETE", req);
}
