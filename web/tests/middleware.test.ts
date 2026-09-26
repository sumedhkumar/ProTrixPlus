import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TOKEN_COOKIE } from "../lib/claims";
import { middleware } from "../middleware";

const makeJwt = (payload: Record<string, unknown>): string => {
  const b64 = (o: unknown) =>
    Buffer.from(JSON.stringify(o))
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  return `${b64({ alg: "HS256" })}.${b64(payload)}.sig`;
};

function requestWithToken(path: string, token?: string): NextRequest {
  const headers = new Headers();
  if (token) headers.set("cookie", `${TOKEN_COOKIE}=${token}`);
  return new NextRequest(new URL(`http://localhost${path}`), { headers });
}

const nowSeconds = () => Math.floor(Date.now() / 1000);

describe("middleware", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("redirects an unauthenticated /admin request to /login", async () => {
    const res = await middleware(requestWithToken("/admin"));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/login");
  });

  it("lets an unauthenticated /dashboard request pass through", async () => {
    const res = await middleware(requestWithToken("/dashboard"));
    expect(res.headers.get("location")).toBeNull();
  });

  it("bounces a non-admin role away from /admin", async () => {
    const token = makeJwt({ sub: "u1", role: "USER", name: "U", exp: nowSeconds() + 3600 });
    const res = await middleware(requestWithToken("/admin", token));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/dashboard");
  });

  it("does nothing when the token has plenty of time left", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const token = makeJwt({
      sub: "u1",
      role: "USER",
      name: "U",
      exp: nowSeconds() + 3600, // full hour left
    });
    await middleware(requestWithToken("/dashboard", token));
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("refreshes and swaps the cookie when the token is close to expiry", async () => {
    const newToken = makeJwt({ sub: "u1", role: "USER", name: "U", exp: nowSeconds() + 3600 });
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: newToken }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const oldToken = makeJwt({
      sub: "u1",
      role: "USER",
      name: "U",
      exp: nowSeconds() + 60, // 1 minute left - inside the refresh threshold
    });
    const res = await middleware(requestWithToken("/dashboard", oldToken));

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/auth/refresh"),
      expect.objectContaining({
        method: "POST",
        headers: { Authorization: `Bearer ${oldToken}` },
      }),
    );
    const setCookie = res.cookies.get(TOKEN_COOKIE);
    expect(setCookie?.value).toBe(newToken);
  });

  it("falls back to passing the request through when the refresh call fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }),
    );
    const oldToken = makeJwt({
      sub: "u1",
      role: "USER",
      name: "U",
      exp: nowSeconds() + 60,
    });
    const res = await middleware(requestWithToken("/dashboard", oldToken));
    expect(res.headers.get("location")).toBeNull();
    expect(res.cookies.get(TOKEN_COOKIE)).toBeUndefined();
  });

  it("falls back gracefully when the refresh call throws (network error)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("network down")),
    );
    const oldToken = makeJwt({
      sub: "u1",
      role: "USER",
      name: "U",
      exp: nowSeconds() + 60,
    });
    const res = await middleware(requestWithToken("/dashboard", oldToken));
    expect(res.headers.get("location")).toBeNull();
  });
});
