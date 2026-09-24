import { redirect } from "next/navigation";

import { AdminTeam } from "@/components/AdminTeam";
import { apiFetch, type AdminUser, type Identity } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function AdminTeamPage() {
  const token = getToken()!;
  const identity = await apiFetch<Identity>("/api/v1/me", token);
  // Managing who else is an admin is SUPER_ADMIN-only - no shared capability
  // like the other tabs (see web/lib/roles.ts's canWrite/canRead groups).
  if (identity.role !== "SUPER_ADMIN") redirect("/admin");

  const users = await apiFetch<AdminUser[]>("/api/v1/admin/users", token);
  const admins = users.filter((u) => u.role !== "USER" || u.extra_roles.length > 0);

  return (
    <>
      <h1>Admin Team</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Invite new admins by email and manage who holds which roles.
      </p>
      <AdminTeam admins={admins} />
    </>
  );
}
