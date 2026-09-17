import { createHash, randomBytes } from "crypto";

import { NextResponse } from "next/server";

function required(name: string) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not configured`);
  return value;
}

export function GET(request: Request) {
  try {
    const issuer = required("AUTH0_ISSUER_BASE_URL").replace(/\/$/, "");
    const clientId = required("AUTH0_CLIENT_ID");
    const audience = required("AUTH0_AUDIENCE");
    const state = randomBytes(32).toString("base64url");
    const verifier = randomBytes(48).toString("base64url");
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    const callback = new URL("/api/auth/callback", request.url).toString();
    const url = new URL(`${issuer}/authorize`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("client_id", clientId);
    url.searchParams.set("redirect_uri", callback);
    url.searchParams.set("scope", "openid profile email");
    url.searchParams.set("audience", audience);
    url.searchParams.set("state", state);
    url.searchParams.set("code_challenge", challenge);
    url.searchParams.set("code_challenge_method", "S256");
    const response = NextResponse.redirect(url);
    response.cookies.set("protrix_auth0_state", state, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/api/auth/callback",
      maxAge: 10 * 60,
    });
    response.cookies.set("protrix_auth0_verifier", verifier, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/api/auth/callback",
      maxAge: 10 * 60,
    });
    return response;
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Auth0 is not configured" }, { status: 503 });
  }
}
