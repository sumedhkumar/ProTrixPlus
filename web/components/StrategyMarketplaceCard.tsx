"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { LiveBalance, Mt5ConnectionView, MyAssignmentView, StrategyView } from "@/lib/api";

import { MultiplierSlider } from "./MultiplierSlider";
import { StrategySetupWizard } from "./StrategySetupWizard";
import { WarningBanner } from "./WarningBanner";

export function StrategyMarketplaceCard({
  strategy,
  assignment,
  mt5Connection,
  liveBalance,
  mt5SetupFeePaid,
}: {
  strategy: StrategyView;
  assignment: MyAssignmentView | undefined;
  mt5Connection: Mt5ConnectionView | null;
  liveBalance: LiveBalance;
  mt5SetupFeePaid: boolean;
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

  async function subscribe() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/me/assignments/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy_id: strategy.id }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `subscribe failed (${res.status})`);
      return;
    }
    router.refresh();
  }

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

      {assignment?.status === "PENDING_APPROVAL" ? (
        <>
          <button
            type="button"
            className="secondary"
            disabled
            title="Waiting for an admin to confirm your subscription payment"
            style={{ width: "100%", opacity: 0.7, cursor: "not-allowed" }}
          >
            🔒 Awaiting Payment Approval
          </button>
          <p style={{ color: "var(--dim)", fontSize: 11.5, marginTop: 8 }}>
            Subscription requested. Complete payment for this strategy - once an admin confirms
            it, you&apos;ll be able to connect MT5 and go live.
          </p>
        </>
      ) : assignment?.status === "SETUP_INCOMPLETE" ? (
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
            Payment confirmed - finish sizing, connect your MT5 account, and confirm to go live.
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
      ) : !mt5SetupFeePaid ? (
        <>
          <button
            type="button"
            className="secondary"
            disabled
            title="Pay the one-time MT5 account setup fee above first"
            style={{ width: "100%", opacity: 0.7, cursor: "not-allowed" }}
          >
            🔒 Pay setup fee to subscribe
          </button>
          <p style={{ color: "var(--dim)", fontSize: 11.5, marginTop: 8 }}>
            Activate your account above (one-time setup fee) before subscribing to any strategy.
          </p>
        </>
      ) : (
        <>
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() => void subscribe()}
            style={{ width: "100%" }}
          >
            {busy ? "Subscribing..." : "⚡ Subscribe"}
          </button>
          <p style={{ color: "var(--dim)", fontSize: 11.5, marginTop: 8 }}>
            Instant request, no admin approval needed to see or request it - but it stays locked
            until you pay and an admin confirms.
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
