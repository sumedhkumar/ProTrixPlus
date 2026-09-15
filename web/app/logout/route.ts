import { NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/auth";

export function GET() {
  // Keep the redirect relative to the current origin. In the standalone
  // server, `req.url` can be built from its bind address (0.0.0.0), which
  // sends browsers to an unusable host after sign-out.
  const res = new NextResponse(null, {
    status: 303,
    headers: { Location: "/login" },
  });
  res.cookies.set(TOKEN_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return res;
}
