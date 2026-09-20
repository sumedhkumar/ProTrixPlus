import { AiCopilotPanel } from "@/components/AiCopilotPanel";
import { LiveMt5PositionsDemo } from "@/components/LiveMt5PositionsDemo";
import { Mt5BalanceCard } from "@/components/Mt5BalanceCard";
import { StrategyMarketplaceCard } from "@/components/StrategyMarketplaceCard";
import {
  apiFetch,
  type Identity,
  type LiveBalance,
  type Mt5ConnectionView,
  type MyAssignmentView,
  type PnlSummary,
  type StrategyView,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

// Fixed illustrative figures - not derived from any real broker balance.
// Shown only because a broker connection doesn't exist yet (see MetaApi
// blocker in docs/FULL-BUILD-PLAN.md); always paired with a "DEMO" tag and
// the real connection status badge, never presented as live.
const DEMO_BALANCE = "24,850.00";
const DEMO_EQUITY = "25,490.00";
const DEMO_FREE_MARGIN = "23,900.00";

export const dynamic = "force-dynamic";

export default async function TradingTerminalPage() {
  const token = getToken()!;

  const [myAssignments, mt5Connection, pnlSummary, strategies, identity, liveBalance] =
    await Promise.all([
      apiFetch<MyAssignmentView[]>("/api/v1/me/assignments", token),
      apiFetch<Mt5ConnectionView | null>("/api/v1/me/mt5-connection", token),
      apiFetch<PnlSummary>("/api/v1/me/pnl-summary", token),
      apiFetch<StrategyView[]>("/api/v1/strategies", token),
      apiFetch<Identity>("/api/v1/me", token),
      apiFetch<LiveBalance>("/api/v1/me/mt5-connection/balance", token),
    ]);
  const strategyById = new Map(strategies.map((s) => [s.id, s]));
  const subscribed = myAssignments
    .map((a) => ({ assignment: a, strategy: strategyById.get(a.strategy_id) }))
    .filter((x): x is { assignment: MyAssignmentView; strategy: StrategyView } => !!x.strategy);

  return (
    <>
      <h1>My Trading Terminal</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Real account data only - fields with no live source yet are labeled, not fabricated.
      </p>

      <div className="stat-grid">
        <Mt5BalanceCard
          connection={mt5Connection}
          displayName={identity.display_name}
          demoBalance={DEMO_BALANCE}
          liveBalance={liveBalance}
        />

        <div className="card">
          <div className="card-head">
            <span className="card-title">Realized Strategy P&amp;L</span>
            <span className="badge-pill badge-neutral">Live</span>
          </div>
          <div className={`stat-value ${Number(pnlSummary.realized_pnl) > 0 ? "green" : ""}`}>
            {pnlSummary.realized_pnl}
          </div>
          <div className="stat-sub-cols">
            <div>
              <div>{pnlSummary.attributable_trades}</div>
              <div>Attributable trades</div>
            </div>
            <div>
              <div>{pnlSummary.match_rate_percent}%</div>
              <div>Match rate</div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <span className="card-title">Active Subscriptions</span>
            <a href="/dashboard/marketplace" className="card-link">
              Browse
            </a>
          </div>
          <div className="stat-value">{myAssignments.length} Strategies</div>
          <div className="stat-sub-cols">
            <div>
              <div>{myAssignments.filter((a) => a.status === "ACTIVE").length}</div>
              <div>Active</div>
            </div>
            <div>
              <div>{myAssignments.filter((a) => a.payment_status === "REVOKED").length}</div>
              <div>Revoked</div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <span className="card-title">Account Equity</span>
            {liveBalance.available ? (
              <span className="badge-pill badge-green">LIVE</span>
            ) : (
              <span className="badge-pill badge-demo">DEMO</span>
            )}
          </div>
          <div className="stat-value">
            ${liveBalance.available ? liveBalance.equity?.toFixed(2) : DEMO_EQUITY}
          </div>
          <div className="stat-sub">
            <span>Free Margin:</span>
            <span style={{ color: "var(--fg)", fontWeight: 700 }}>
              ${liveBalance.available ? liveBalance.free_margin?.toFixed(2) : DEMO_FREE_MARGIN}
            </span>
          </div>
        </div>
      </div>

      <AiCopilotPanel displayName={identity.display_name} accountBalance={DEMO_BALANCE} />

      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-head">
          <span className="card-title">Subscribed strategies &amp; multiplier controls</span>
          <a href="/dashboard/marketplace" className="card-link">
            Marketplace &amp; multipliers →
          </a>
        </div>
        {subscribed.length === 0 ? (
          <div className="empty">
            No strategies granted yet - see the Strategy Marketplace tab, or ask an admin.
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
            {subscribed.map(({ assignment, strategy }) => (
              <StrategyMarketplaceCard
                key={assignment.id}
                strategy={strategy}
                assignment={assignment}
                mt5Connection={mt5Connection}
              />
            ))}
          </div>
        )}
      </div>

      <LiveMt5PositionsDemo />
    </>
  );
}
