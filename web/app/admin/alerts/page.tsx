import { AdminAlertCatalog } from "@/components/AdminAlertCatalog";
import { apiFetch, type AlertView } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function AlertCatalogPage() {
  const token = getToken()!;
  const alerts = await apiFetch<AlertView[]>("/api/v1/admin/alerts", token);

  return (
    <>
      <h1>Alert Catalog</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Capture and version TradingView alert configs, then bundle them into a strategy from the
        Strategy Lifecycle tab.
      </p>
      <AdminAlertCatalog alerts={alerts} />
    </>
  );
}
