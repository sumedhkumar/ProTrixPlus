import { NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/auth";

export function GET(request: Request) {
  // Keep the redirect relative to the current origin. In the standalone
  // server, `req.url` can be built from its bind address (0.0.0.0), which
  // sends browsers to an unusable host after sign-out.
  const issuer = process.env.AUTH0_ISSUER_BASE_URL?.replace(/\/$/, "");
  const clientId = process.env.AUTH0_CLIENT_ID;
  const auth0Logout = issuer && clientId
    ? `${issuer}/v2/logout?${new URLSearchParams({ client_id: clientId, returnTo: new URL("/login", request.url).toString() }).toString()}`
    : "/login";
  const res = new NextResponse(null, {
    status: 303,
    headers: { Location: auth0Logout },
  });
  res.cookies.set(TOKEN_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return res;
}
