import { AdminStrategyCatalog } from "@/components/AdminStrategyCatalog";
import { apiFetch, type AlertView, type Identity, type StrategyView } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { canWrite } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function StrategyLifecyclePage() {
  const token = getToken()!;
  const [strategies, alerts, identity] = await Promise.all([
    apiFetch<StrategyView[]>("/api/v1/admin/strategies", token),
    apiFetch<AlertView[]>("/api/v1/admin/alerts", token).catch(() => []),
    apiFetch<Identity>("/api/v1/me", token),
  ]);

  return (
    <>
      <h1>Strategy Lifecycle &amp; Catalog Management</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Centrally publish, price, and toggle strategies ON/OFF. TradingView alert mapping is
        available per strategy without exposing the webhook secret.
      </p>
      <AdminStrategyCatalog
        strategies={strategies}
        alerts={alerts}
        canEdit={canWrite(identity.role, "strategy", identity.extra_roles)}
      />
    </>
  );
}
