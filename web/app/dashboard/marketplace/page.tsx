import { StrategyMarketplaceCard } from "@/components/StrategyMarketplaceCard";
import {
  apiFetch,
  type Mt5ConnectionView,
  type MyAssignmentView,
  type StrategyView,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function MarketplacePage() {
  const token = getToken()!;
  const [strategies, myAssignments, mt5Connection] = await Promise.all([
    apiFetch<StrategyView[]>("/api/v1/strategies", token),
    apiFetch<MyAssignmentView[]>("/api/v1/me/assignments", token),
    apiFetch<Mt5ConnectionView | null>("/api/v1/me/mt5-connection", token).catch(() => null),
  ]);
  const byStrategyId = new Map(myAssignments.map((a) => [a.strategy_id, a]));

  return (
    <>
      <h1>Strategy Marketplace</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Centrally managed strategies. Select your exposure multiplier where you have been granted
        access.
      </p>
      {strategies.length === 0 ? (
        <div className="pending-panel">No strategies published yet.</div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
            gap: 16,
          }}
        >
          {strategies.map((s) => (
            <StrategyMarketplaceCard
              key={s.id}
              strategy={s}
              assignment={byStrategyId.get(s.id)}
              mt5Connection={mt5Connection}
            />
          ))}
        </div>
      )}
    </>
  );
}
