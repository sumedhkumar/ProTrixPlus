/**
 * Pure role-routing helpers. Unit-tested (tests/roles.test.ts). No I/O.
 * The real authorization gate is the api; this only decides client navigation
 * and which controls to render. Capability groups below mirror the api's
 * _OPS/_STRATEGY/_FINANCE dependency groups in app/routers/admin.py.
 */

export type Role =
  | "USER"
  | "SUPER_ADMIN"
  | "OPERATIONS_ADMIN"
  | "STRATEGY_ADMIN"
  | "FINANCE_ADMIN"
  | "AUDITOR";

export const ROLES: readonly Role[] = [
  "USER",
  "SUPER_ADMIN",
  "OPERATIONS_ADMIN",
  "STRATEGY_ADMIN",
  "FINANCE_ADMIN",
  "AUDITOR",
] as const;

export function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as readonly string[]).includes(value);
}

const ADMIN_ROLES: readonly Role[] = [
  "SUPER_ADMIN",
  "OPERATIONS_ADMIN",
  "STRATEGY_ADMIN",
  "FINANCE_ADMIN",
  "AUDITOR",
];

export function canAccessAdmin(role: Role | null | undefined): boolean {
  return !!role && ADMIN_ROLES.includes(role);
}

/** Functional capability groups, matching the api's per-route dependencies. */
export type Capability = "ops" | "strategy" | "finance";

const CAPABILITY_ROLES: Record<Capability, readonly Role[]> = {
  ops: ["SUPER_ADMIN", "OPERATIONS_ADMIN"],
  strategy: ["SUPER_ADMIN", "STRATEGY_ADMIN"],
  finance: ["SUPER_ADMIN", "FINANCE_ADMIN"],
};

/**
 * Can this role submit writes (create/update/approve/etc.) for `capability`?
 * `extraRoles` covers a multi-role admin's grants beyond their primary role
 * (see UserRoleGrant / the api's require_role, which unions both) - without
 * it, a STRATEGY_ADMIN also granted FINANCE_ADMIN as an extra role would be
 * shown read-only finance controls despite the api accepting their writes.
 */
export function canWrite(
  role: Role | null | undefined,
  capability: Capability,
  extraRoles: readonly Role[] = [],
): boolean {
  if (!role) return false;
  return (
    CAPABILITY_ROLES[capability].includes(role) ||
    extraRoles.some((r) => CAPABILITY_ROLES[capability].includes(r))
  );
}

/** Can this role at least view `capability`'s data (write access, or AUDITOR)? */
export function canRead(
  role: Role | null | undefined,
  capability: Capability,
  extraRoles: readonly Role[] = [],
): boolean {
  return canWrite(role, capability, extraRoles) || role === "AUDITOR" || extraRoles.includes("AUDITOR");
}

export function homePathForRole(role: Role | null | undefined): string {
  return canAccessAdmin(role) ? "/admin" : "/dashboard";
}

/** Where to send someone who asked for `requestedPath` but is not allowed. */
export function redirectForForbidden(role: Role | null | undefined): string {
  return role ? homePathForRole(role) : "/login";
}
