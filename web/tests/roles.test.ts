import { describe, expect, it } from "vitest";

import {
  canAccessAdmin,
  homePathForRole,
  isRole,
  redirectForForbidden,
} from "../lib/roles";
import { decodeClaims } from "../lib/claims";

describe("roles", () => {
  it("only SUPER_ADMIN can access admin", () => {
    expect(canAccessAdmin("SUPER_ADMIN")).toBe(true);
    expect(canAccessAdmin("USER")).toBe(false);
    expect(canAccessAdmin(null)).toBe(false);
  });

  it("routes each role to its home", () => {
    expect(homePathForRole("SUPER_ADMIN")).toBe("/admin");
    expect(homePathForRole("USER")).toBe("/dashboard/marketplace");
  });

  it("bounces a forbidden USER to their own dashboard, anon to login", () => {
    expect(redirectForForbidden("USER")).toBe("/dashboard/marketplace");
    expect(redirectForForbidden(null)).toBe("/login");
  });

  it("validates role strings", () => {
    expect(isRole("USER")).toBe(true);
    expect(isRole("root")).toBe(false);
  });
});

describe("decodeClaims", () => {
  const makeJwt = (payload: Record<string, unknown>): string => {
    const b64 = (o: unknown) =>
      Buffer.from(JSON.stringify(o))
        .toString("base64")
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
    return `${b64({ alg: "HS256" })}.${b64(payload)}.sig`;
  };

  it("reads sub/role/name from an unverified payload", () => {
    const token = makeJwt({ sub: "u-1", role: "SUPER_ADMIN", name: "Root", exp: 42 });
    expect(decodeClaims(token)).toEqual({
      subject: "u-1",
      role: "SUPER_ADMIN",
      displayName: "Root",
      email: "",
      expiresAt: 42,
    });
  });

  it("rejects garbage and unknown roles", () => {
    expect(decodeClaims("nope")).toBeNull();
    expect(decodeClaims(makeJwt({ sub: "x", role: "hacker" }))).toBeNull();
    expect(decodeClaims(undefined)).toBeNull();
  });
});
