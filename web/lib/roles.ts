/**
 * Pure role-routing helpers. Unit-tested (tests/roles.test.ts). No I/O.
 * The real authorization gate is the api; this only decides client navigation.
 */

export type Role = "USER" | "SUPER_ADMIN";

export const ROLES: readonly Role[] = ["USER", "SUPER_ADMIN"] as const;

export function isRole(value: unknown): value is Role {
  return value === "USER" || value === "SUPER_ADMIN";
}

export function canAccessAdmin(role: Role | null | undefined): boolean {
  return role === "SUPER_ADMIN";
}

export function homePathForRole(role: Role | null | undefined): string {
  return role === "SUPER_ADMIN" ? "/admin" : "/dashboard/marketplace";
}

/** Where to send someone who asked for `requestedPath` but is not allowed. */
export function redirectForForbidden(role: Role | null | undefined): string {
  return role ? homePathForRole(role) : "/login";
}
