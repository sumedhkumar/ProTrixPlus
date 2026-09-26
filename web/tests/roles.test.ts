import { describe, expect, it } from "vitest";

import {
  canAccessAdmin,
  canRead,
  canWrite,
  homePathForRole,
  isRole,
  redirectForForbidden,
} from "../lib/roles";
import { decodeClaims } from "../lib/claims";

describe("roles", () => {
  it("any admin tier can access admin, USER cannot", () => {
    for (const role of [
      "SUPER_ADMIN",
      "OPERATIONS_ADMIN",
      "STRATEGY_ADMIN",
      "FINANCE_ADMIN",
      "AUDITOR",
    ] as const) {
      expect(canAccessAdmin(role)).toBe(true);
    }
    expect(canAccessAdmin("USER")).toBe(false);
    expect(canAccessAdmin(null)).toBe(false);
  });

  it("routes each role to its home", () => {
    expect(homePathForRole("SUPER_ADMIN")).toBe("/admin");
    expect(homePathForRole("OPERATIONS_ADMIN")).toBe("/admin");
    expect(homePathForRole("USER")).toBe("/dashboard/marketplace");
  });

  it("bounces a forbidden USER to their own dashboard, anon to login", () => {
    expect(redirectForForbidden("USER")).toBe("/dashboard/marketplace");
    expect(redirectForForbidden(null)).toBe("/login");
  });

  it("validates role strings", () => {
    expect(isRole("USER")).toBe(true);
    expect(isRole("AUDITOR")).toBe(true);
    expect(isRole("root")).toBe(false);
  });

  it("gates writes to the role that owns each capability, plus SUPER_ADMIN", () => {
    expect(canWrite("STRATEGY_ADMIN", "strategy")).toBe(true);
    expect(canWrite("SUPER_ADMIN", "strategy")).toBe(true);
    expect(canWrite("OPERATIONS_ADMIN", "strategy")).toBe(false);
    expect(canWrite("FINANCE_ADMIN", "ops")).toBe(false);
    expect(canWrite("AUDITOR", "finance")).toBe(false);
  });

  it("lets AUDITOR read every capability but write none", () => {
    for (const capability of ["ops", "strategy", "finance"] as const) {
      expect(canRead("AUDITOR", capability)).toBe(true);
      expect(canWrite("AUDITOR", capability)).toBe(false);
    }
    expect(canRead("USER", "ops")).toBe(false);
  });

  it("also grants write/read from a multi-role admin's extra roles", () => {
    // STRATEGY_ADMIN primary, FINANCE_ADMIN as an extra UserRoleGrant.
    expect(canWrite("STRATEGY_ADMIN", "finance")).toBe(false);
    expect(canWrite("STRATEGY_ADMIN", "finance", ["FINANCE_ADMIN"])).toBe(true);
    expect(canRead("STRATEGY_ADMIN", "finance", ["FINANCE_ADMIN"])).toBe(true);
    expect(canRead("STRATEGY_ADMIN", "ops", ["AUDITOR"])).toBe(true);
    expect(canWrite("STRATEGY_ADMIN", "ops", ["AUDITOR"])).toBe(false);
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
