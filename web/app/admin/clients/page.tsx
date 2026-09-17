import { AdminClientsOverview } from "@/components/AdminClientsOverview";
import { AdminGrantEntitlement } from "@/components/AdminGrantEntitlement";
import {
  apiFetch,
  type AdminAssignment,
  type AdminMt5ConnectionView,
  type AdminUser,
  type StrategyView,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function ClientsPage() {
  const token = getToken()!;
  const [users, assignments, strategies, mt5Connections] = await Promise.all([
    apiFetch<AdminUser[]>("/api/v1/admin/users", token),
    apiFetch<AdminAssignment[]>("/api/v1/admin/assignments", token),
    apiFetch<StrategyView[]>("/api/v1/admin/strategies", token),
    apiFetch<AdminMt5ConnectionView[]>("/api/v1/admin/mt5-connections", token),
  ]);

  return (
    <>
      <h1>Clients, Risk Caps &amp; Entitlements</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Manage individual client entitlements and see MT5 bridge status. &ldquo;Kill switch&rdquo;
        (an immediate force-disable, distinct from revoking a strategy entitlement) is not built
        yet - revoking a specific strategy below is real and functional.
      </p>
      <AdminClientsOverview users={users} assignments={assignments} mt5Connections={mt5Connections} />
      <div style={{ marginTop: 16 }}>
        <AdminGrantEntitlement users={users} strategies={strategies} assignments={assignments} />
      </div>
    </>
  );
}
