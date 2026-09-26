"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { Mt5ConnectionView, MyAssignmentView, StrategyView } from "@/lib/api";

import { StrategySetupWizard } from "./StrategySetupWizard";

const MULTIPLIERS = [1, 2, 3, 5, 10, 20] as const;
type Multiplier = (typeof MULTIPLIERS)[number];

export function StrategyMarketplaceCard({
  strategy,
  assignment,
  mt5Connection,
}: {
  strategy: StrategyView;
  assignment: MyAssignmentView | undefined;
  mt5Connection: Mt5ConnectionView | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [selectedMultiplier, setSelectedMultiplier] = useState<Multiplier>(
    (Number(assignment?.multiplier ?? 1) as Multiplier) || 1,
  );
  const [previewLot, setPreviewLot] = useState<string | null>(
    assignment ? assignment.effective_lot : null,
  );

  const masterLot = assignment?.master_lot ?? strategy.base_lot;
  const multiplierMin = assignment?.multiplier_min ?? "1";
  const multiplierMax = assignment?.multiplier_max ?? "3";

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
        <code>
          {strategy.strategy_key}@{strategy.strategy_version}
        </code>
      </div>
      {strategy.description ? (
        <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 16 }}>{strategy.description}</p>
      ) : null}

      <div className="stat-sub" style={{ marginBottom: 10 }}>
        <span>Exposure multiplier</span>
        <span>Base lot: {masterLot ?? "—"}</span>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {MULTIPLIERS.map((m) => {
          const active = selectedMultiplier === m;
          const inBounds = m >= Number(multiplierMin) && m <= Number(multiplierMax);
          return (
            <button
              key={m}
              type="button"
              className={active ? "btn-primary" : "secondary"}
              disabled={!inBounds || busy}
              onClick={() => setSelectedMultiplier(m)}
              style={{ flex: "1 1 60px" }}
            >
              {m}X
            </button>
          );
        })}
      </div>
      <div className="stat-sub" style={{ marginBottom: 16 }}>
        <span>Projected Execution Lot Sizing</span>
        <span style={{ color: "var(--fg)", fontWeight: 700 }}>
          {masterLot ?? "—"}L × {selectedMultiplier}X ={" "}
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
          strategyName={strategy.name}
          assignment={assignment}
          mt5Connection={mt5Connection}
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
