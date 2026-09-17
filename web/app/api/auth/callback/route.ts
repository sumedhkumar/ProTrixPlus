import { NextRequest, NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/auth";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const expectedState = request.cookies.get("protrix_auth0_state")?.value;
  const verifier = request.cookies.get("protrix_auth0_verifier")?.value;
  const issuer = process.env.AUTH0_ISSUER_BASE_URL?.replace(/\/$/, "");
  const clientId = process.env.AUTH0_CLIENT_ID;
  const clientSecret = process.env.AUTH0_CLIENT_SECRET;
  const audience = process.env.AUTH0_AUDIENCE;
  if (!code || !state || !expectedState || state !== expectedState || !verifier || !issuer || !clientId || !clientSecret || !audience) {
    return NextResponse.redirect(new URL("/login?error=auth0", request.url));
  }
  try {
    const callback = new URL("/api/auth/callback", request.url).toString();
    const body = new URLSearchParams({ grant_type: "authorization_code", client_id: clientId, client_secret: clientSecret, code, redirect_uri: callback, audience, code_verifier: verifier });
    const exchange = await fetch(`${issuer}/oauth/token`, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body, cache: "no-store" });
    const payload = (await exchange.json().catch(() => ({}))) as { access_token?: unknown; expires_in?: unknown };
    if (!exchange.ok || typeof payload.access_token !== "string") throw new Error("token exchange failed");
    const response = NextResponse.redirect(new URL("/dashboard", request.url));
    response.cookies.set(TOKEN_COOKIE, payload.access_token, { httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge: typeof payload.expires_in === "number" ? payload.expires_in : 3600 });
    response.cookies.set("protrix_auth0_state", "", { httpOnly: true, path: "/api/auth/callback", maxAge: 0 });
    response.cookies.set("protrix_auth0_verifier", "", { httpOnly: true, path: "/api/auth/callback", maxAge: 0 });
    return response;
  } catch {
    return NextResponse.redirect(new URL("/login?error=auth0", request.url));
  }
}
