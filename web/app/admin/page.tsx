import { AdminStrategyCatalog } from "@/components/AdminStrategyCatalog";
import { apiFetch, type StrategyView } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function StrategyLifecyclePage() {
  const token = getToken()!;
  const strategies = await apiFetch<StrategyView[]>("/api/v1/admin/strategies", token);

  return (
    <>
      <h1>Strategy Lifecycle &amp; Catalog Management</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Centrally publish, price, and toggle strategies ON/OFF. TradingView alert mapping is
        available per strategy without exposing the webhook secret.
      </p>
      <AdminStrategyCatalog strategies={strategies} />
    </>
  );
}
