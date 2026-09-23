"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { LiveBalance, Mt5ConnectionView, MyAssignmentView, StrategyView } from "@/lib/api";

import { MultiplierSlider } from "./MultiplierSlider";
import { StrategySetupWizard } from "./StrategySetupWizard";
import { WarningBanner } from "./WarningBanner";

// Deterministic (per-strategy-id, not random-per-render) illustrative stats.
// No real trade-performance analytics or AI regime model exist yet - always
// shown with a DEMO tag, same convention as AiCopilotPanel's Market Radar.
const REGIMES = [
  "Trend Expansion",
  "Mean-Reversion",
  "Volatility Squeeze",
  "Momentum Breakout",
  "Range Compression",
  "Institutional Accumulation",
];

function demoStats(seed: string): {
  winRate: string;
  profitFactor: string;
  trades: number;
  regimeFitness: number;
  regime: string;
  recommendedMultiplier: 1 | 2 | 3;
} {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) & 0xffffffff;
  const winRate = (55 + (Math.abs(hash) % 20)).toFixed(1);
  const profitFactor = (1.3 + (Math.abs(hash >> 4) % 90) / 100).toFixed(2);
  const trades = 90 + (Math.abs(hash >> 8) % 150);
  const regimeFitness = 80 + (Math.abs(hash >> 12) % 18);
  const regime = REGIMES[Math.abs(hash >> 16) % REGIMES.length] ?? "Trend Expansion";
  const recommendedMultiplier = ((Math.abs(hash >> 20) % 3) + 1) as 1 | 2 | 3;
  return { winRate, profitFactor, trades, regimeFitness, regime, recommendedMultiplier };
}

export function StrategyMarketplaceCard({
  strategy,
  assignment,
  mt5Connection,
  liveBalance,
}: {
  strategy: StrategyView;
  assignment: MyAssignmentView | undefined;
  mt5Connection: Mt5ConnectionView | null;
  liveBalance: LiveBalance;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [selectedMultiplier, setSelectedMultiplier] = useState<number>(
    Number(assignment?.multiplier ?? 1) || 1,
  );
  const [previewLot, setPreviewLot] = useState<string | null>(
    assignment ? assignment.effective_lot : null,
  );

  const masterLot = assignment?.master_lot ?? strategy.base_lot;
  const multiplierMin = assignment?.multiplier_min ?? "1";
  const multiplierMax = assignment?.multiplier_max ?? "3";
  // What actually gets used/saved - the slider itself now spans 1X-100X, but
  // the backend still clamps to the admin-granted range per assignment
  // (protrix_contracts.money.compute_lot), so the displayed equation must
  // reflect that clamp too, not the raw slider value, or the math looks
  // broken (e.g. "0.10L x 100X = 0.30 Lots").
  const effectiveMultiplier = Math.min(
    Number(multiplierMax),
    Math.max(Number(multiplierMin), selectedMultiplier),
  );
  const multiplierCapped = effectiveMultiplier !== selectedMultiplier;

  useEffect(() => {
    if (!masterLot) {
      setPreviewLot(null);
      return;
    }
    let cancelled = false;
    void fetch("/api/me/assignments/preview-lot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        master_lot: masterLot,
        multiplier: selectedMultiplier,
        multiplier_min: multiplierMin,
        multiplier_max: multiplierMax,
      }),
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((body: { effective_lot?: string } | null) => {
        if (!cancelled) setPreviewLot(body?.effective_lot ?? null);
      })
      .catch(() => {
        if (!cancelled) setPreviewLot(null);
      });
    return () => {
      cancelled = true;
    };
  }, [masterLot, multiplierMin, multiplierMax, selectedMultiplier]);

  async function updateSizing() {
    if (!assignment) return;
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/me/assignments/${assignment.id}/multiplier`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ multiplier: selectedMultiplier }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  const stats = demoStats(strategy.id);
  const sizingChanged = assignment ? selectedMultiplier !== Number(assignment.multiplier) : false;
  const belowMinBalance =
    strategy.min_balance !== null &&
    liveBalance.available &&
    liveBalance.balance !== undefined &&
    liveBalance.balance < Number(strategy.min_balance);

  return (
    <div className="card">
      <div className="card-head">
        <span style={{ fontSize: 16, fontWeight: 800 }}>{strategy.name}</span>
        <span className={`badge-pill ${strategy.is_active ? "badge-green" : "badge-neutral"}`}>
          Strategy: {strategy.is_active ? "ACTIVE" : "OFF"}
        </span>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        {strategy.symbol ? <span className="badge-pill badge-blue">{strategy.symbol}</span> : null}
        {strategy.timeframe ? <span className="badge-pill badge-neutral">{strategy.timeframe}</span> : null}
        {strategy.min_balance ? (
          <span
            className={`badge-pill ${belowMinBalance ? "badge-warn" : "badge-neutral"}`}
            title="Minimum MT5 account balance required for this strategy to work"
          >
            Min. balance: ${strategy.min_balance}
          </span>
        ) : null}
        <code>
          {strategy.strategy_key}@{strategy.strategy_version}
        </code>
      </div>
      {strategy.description ? (
        <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 16 }}>{strategy.description}</p>
      ) : null}
      {belowMinBalance ? (
        <WarningBanner
          tone="bad"
          title="Balance below minimum"
          message={`Your connected MT5 account balance ($${liveBalance.balance?.toFixed(2)}) is below the $${strategy.min_balance} this strategy requires - fund your account before starting it.`}
        />
      ) : null}

      <div className="stat-sub-cols" style={{ marginBottom: 14 }}>
        <div>
          <div>{strategy.win_rate ?? stats.winRate}%</div>
          <div>Win rate{strategy.win_rate ? "" : " (demo)"}</div>
        </div>
        <div>
          <div>{strategy.max_drawdown ? `${strategy.max_drawdown}%` : stats.profitFactor}</div>
          <div>{strategy.max_drawdown ? "Max drawdown" : "Profit factor (demo)"}</div>
        </div>
        <div>
          <div>{stats.trades}</div>
          <div>Track record (demo)</div>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 10,
          background: "rgba(124, 108, 246, 0.08)",
          border: "1px solid var(--panel-border)",
          borderRadius: 10,
          padding: "10px 14px",
          marginBottom: 14,
        }}
      >
        <div>
          <div style={{ fontSize: 12.5, fontWeight: 700 }}>
            ✨ AI Regime Fitness: {stats.regimeFitness}% ({stats.regime})
            <span className="badge-pill badge-demo" style={{ marginLeft: 6 }}>
              DEMO
            </span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--muted)" }}>
            Kelly Criterion: {stats.recommendedMultiplier}X optimal multiplier recommended - illustrative, not a real model.
          </div>
        </div>
        <span className="mult-badge" style={{ whiteSpace: "nowrap" }}>
          {stats.recommendedMultiplier}X OPTIMAL
        </span>
      </div>

      <div className="stat-sub" style={{ marginBottom: 10 }}>
        <span>Exposure multiplier</span>
        <span>Base lot: {masterLot ?? "—"}</span>
      </div>
      <MultiplierSlider value={selectedMultiplier} onChange={setSelectedMultiplier} disabled={busy} />
      {multiplierCapped ? (
        <WarningBanner
          tone="warn"
          title={`Capped to ${effectiveMultiplier}X`}
          message={`Your account is entitled to ${multiplierMin}X-${multiplierMax}X on this strategy - ${selectedMultiplier}X will be capped to ${effectiveMultiplier}X. Ask an admin to raise your limit for more.`}
        />
      ) : null}
      <div className="stat-sub" style={{ marginBottom: 16 }}>
        <span>Projected Execution Lot Sizing</span>
        <span style={{ color: "var(--fg)", fontWeight: 700 }}>
          {masterLot ?? "—"}L × {effectiveMultiplier}X ={" "}
          {previewLot !== null ? `${previewLot} Lots` : "—"}
        </span>
      </div>

      {assignment?.status === "SETUP_INCOMPLETE" ? (
        <>
          <button
            type="button"
            className="btn-primary"
            onClick={() => setShowWizard(true)}
            style={{ width: "100%" }}
          >
            ⚡ Complete Setup →
          </button>
          <p style={{ color: "var(--dim)", fontSize: 11.5, marginTop: 8 }}>
            Access granted - finish sizing, connect your MT5 account, and confirm to go live.
          </p>
        </>
      ) : assignment ? (
        <>
          {assignment.status === "ACTIVE" ? (
            <span className="badge-pill badge-green" style={{ marginBottom: 8, display: "inline-block" }}>
              🟢 Live
            </span>
          ) : null}
          <button
            type="button"
            className="btn-primary"
            disabled={!sizingChanged || busy}
            onClick={() => void updateSizing()}
            style={{ width: "100%" }}
          >
            {busy ? "Saving..." : `⟳ Update Sizing (${selectedMultiplier}X)`}
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            className="secondary"
            disabled
            title="Self-serve activation isn't live in this MVP - access is admin-granted. Ask an admin under Clients & Risk Caps."
            style={{ width: "100%", opacity: 0.6, cursor: "not-allowed" }}
          >
            🔒 Activate &amp; Route to MT5
          </button>
          <p style={{ color: "var(--dim)", fontSize: 11.5, marginTop: 8 }}>
            Not activated for your account yet - this MVP has no self-serve checkout; ask an admin
            to grant it after payment.
          </p>
        </>
      )}

      {showWizard && assignment ? (
        <StrategySetupWizard
          strategy={strategy}
          assignment={assignment}
          mt5Connection={mt5Connection}
          liveBalance={liveBalance}
          onClose={() => setShowWizard(false)}
        />
      ) : null}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 16,
          paddingTop: 12,
          borderTop: "1px solid var(--panel-border)",
        }}
      >
        <div>
          <span style={{ fontSize: 20, fontWeight: 800 }}>
            {strategy.price ? `$${strategy.price}` : "—"}
          </span>
          {strategy.profit_share_percent ? (
            <span style={{ color: "var(--muted)", fontSize: 12 }}>
              {" "}
              /month + {strategy.profit_share_percent}% realized profit-share
            </span>
          ) : null}
        </div>
        {error ? <span style={{ color: "var(--bad)", fontSize: 12 }}>{error}</span> : null}
      </div>
    </div>
  );
}
