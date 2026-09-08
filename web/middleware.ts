import { NextResponse, type NextRequest } from "next/server";

import { decodeClaims, TOKEN_COOKIE } from "@/lib/claims";
import { canAccessAdmin } from "@/lib/roles";

/**
 * Edge guard for /admin/*. A USER (or anonymous) request is bounced before the
 * page renders. This is defence-in-depth; the api is the authoritative gate.
 */
export function middleware(req: NextRequest) {
  const claims = decodeClaims(req.cookies.get(TOKEN_COOKIE)?.value);
  if (!claims) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  if (!canAccessAdmin(claims.role)) {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*"],
};
