import { NextResponse, type NextRequest } from "next/server";

import { decodeClaims, TOKEN_COOKIE } from "@/lib/claims";
import { canAccessAdmin } from "@/lib/roles";

const API_URL = process.env.PROTRIX_API_URL ?? "http://localhost:8000";
// The token's own TTL is 1 hour (api/app/config.py's dev_jwt_ttl_seconds).
// Refreshing once this little time is left means an actively-used session
// renews well before it actually expires, instead of racing the clock on
// every single request.
const REFRESH_THRESHOLD_SECONDS = 15 * 60;
const COOKIE_MAX_AGE_SECONDS = 60 * 60;

/**
 * Edge guard for /admin/* and sliding-session renewal for /dashboard/* and
 * /admin/*. A USER (or anonymous) request to /admin is bounced before the
 * page renders - defence-in-depth, the api is the authoritative gate.
 *
 * Renewal: the login cookie was previously set once, for a fixed 1 hour,
 * and never touched again - so an actively-used session could still expire
 * mid-action once that fixed timer ran out, regardless of activity. When
 * the current token is close to its own expiry, this calls the api's
 * POST /auth/refresh (using the still-valid token) and replaces the cookie
 * with the fresh one it returns - a real new token with a new exp, not
 * just a longer-lived cookie wrapping the same now-stale one.
 */
export async function middleware(req: NextRequest) {
  const token = req.cookies.get(TOKEN_COOKIE)?.value;
  const claims = decodeClaims(token);
  const isAdminPath = req.nextUrl.pathname.startsWith("/admin");

  if (!claims) {
    return isAdminPath ? NextResponse.redirect(new URL("/login", req.url)) : NextResponse.next();
  }
  if (isAdminPath && !canAccessAdmin(claims.role)) {
    return NextResponse.redirect(new URL("/dashboard", req.url));
  }

  const secondsRemaining = claims.expiresAt - Math.floor(Date.now() / 1000);
  if (secondsRemaining > REFRESH_THRESHOLD_SECONDS) {
    return NextResponse.next();
  }

  const refreshed = await refreshedResponse(token!);
  return refreshed ?? NextResponse.next();
}

async function refreshedResponse(token: string): Promise<NextResponse | null> {
  try {
    const res = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { access_token?: unknown };
    if (typeof body.access_token !== "string") return null;

    const response = NextResponse.next();
    response.cookies.set(TOKEN_COOKIE, body.access_token, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: COOKIE_MAX_AGE_SECONDS,
    });
    return response;
  } catch {
    // A network hiccup here must not break the request - the page's own
    // auth check still runs and handles a genuinely expired/invalid token.
    return null;
  }
}

export const config = {
  matcher: ["/dashboard/:path*", "/admin/:path*"],
};
