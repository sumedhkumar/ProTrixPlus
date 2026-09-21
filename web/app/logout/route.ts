import { NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/auth";

export function GET(req: Request) {
  // req.url resolves against the container's bind address (0.0.0.0) rather
  // than the Host header the browser actually sent, so build the redirect
  // from the request headers instead - same approach as middleware.ts's
  // NextRequest-based redirects, which don't hit this because the edge
  // runtime fills in req.url from Host for us.
  const host = req.headers.get("host") ?? "localhost:3000";
  const proto = req.headers.get("x-forwarded-proto") ?? "http";
  const res = NextResponse.redirect(new URL("/login", `${proto}://${host}`));
  res.cookies.set(TOKEN_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
