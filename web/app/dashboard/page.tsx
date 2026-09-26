import { AllStrategiesPanel } from "@/components/AllStrategiesPanel";
import { Mt5BalanceCard } from "@/components/Mt5BalanceCard";
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

  return (
    <>
      <h1>My Trading Terminal</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Real account data only - fields with no live source yet are labeled, not fabricated.
      </p>

      <div className="stat-grid">
        <Mt5BalanceCard connection={mt5Connection} liveBalance={liveBalance} />

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
              <span className="badge-pill badge-neutral">Not available</span>
            )}
          </div>
          {liveBalance.available ? (
            <>
              <div className="stat-value">${liveBalance.equity?.toFixed(2)}</div>
              <div className="stat-sub">
                <span>Free Margin:</span>
                <span style={{ color: "var(--fg)", fontWeight: 700 }}>
                  ${liveBalance.free_margin?.toFixed(2)}
                </span>
              </div>
            </>
          ) : (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>
              {liveBalance.reason ?? "Connect a live MT5 account to see equity here."}
            </div>
          )}
        </div>
      </div>

      <AllStrategiesPanel
        strategies={strategies}
        myAssignments={myAssignments}
        mt5Connection={mt5Connection}
        liveBalance={liveBalance}
        mt5SetupFeePaid={identity.mt5_setup_fee_paid}
      />
    </>
  );
}
