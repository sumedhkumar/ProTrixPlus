import { AdminClientsOverview } from "@/components/AdminClientsOverview";
import { AdminGrantEntitlement } from "@/components/AdminGrantEntitlement";
import {
  apiFetch,
  type AdminAssignment,
  type AdminMt5ConnectionView,
  type AdminUser,
  type Identity,
  type StrategyView,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { canWrite } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function ClientsPage() {
  const token = getToken()!;
  const [users, assignments, strategies, mt5Connections, identity] = await Promise.all([
    apiFetch<AdminUser[]>("/api/v1/admin/users", token),
    apiFetch<AdminAssignment[]>("/api/v1/admin/assignments", token),
    apiFetch<StrategyView[]>("/api/v1/admin/strategies", token),
    apiFetch<AdminMt5ConnectionView[]>("/api/v1/admin/mt5-connections", token),
    apiFetch<Identity>("/api/v1/me", token),
  ]);

  return (
    <>
      <h1>Clients, Risk Caps &amp; Entitlements</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Manage individual client entitlements and see MT5 bridge status.
        Deactivating an account (SUPER_ADMIN only) is an immediate account-wide
        block, distinct from revoking a single strategy entitlement below.
      </p>
      <AdminClientsOverview
        users={users}
        assignments={assignments}
        mt5Connections={mt5Connections}
        canDeactivate={identity.role === "SUPER_ADMIN"}
      />
      <div style={{ marginTop: 16 }}>
        <AdminGrantEntitlement
          users={users}
          strategies={strategies}
          assignments={assignments}
          canManage={canWrite(identity.role, "finance", identity.extra_roles)}
        />
      </div>
    </>
  );
}
