import { AdminAlertCatalog } from "@/components/AdminAlertCatalog";
import { apiFetch, type AlertView, type Identity } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { canWrite } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function AlertCatalogPage() {
  const token = getToken()!;
  const [alerts, identity] = await Promise.all([
    apiFetch<AlertView[]>("/api/v1/admin/alerts", token),
    apiFetch<Identity>("/api/v1/me", token),
  ]);

  return (
    <>
      <h1>Alert Catalog</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Capture and version TradingView alert configs, then bundle them into a strategy from the
        Strategy Lifecycle tab.
      </p>
      <AdminAlertCatalog
        alerts={alerts}
        canEdit={canWrite(identity.role, "strategy", identity.extra_roles)}
      />
    </>
  );
}
