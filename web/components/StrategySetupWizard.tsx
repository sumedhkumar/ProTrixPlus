"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { LiveBalance, Mt5ConnectionView, MyAssignmentView, StrategyView } from "@/lib/api";

import { Mt5ConnectionModal } from "./Mt5ConnectionModal";
import { MultiplierSlider } from "./MultiplierSlider";
import { WarningBanner } from "./WarningBanner";

function RiskConfirmModal({
  strategyName,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  strategyName: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(4,6,10,0.8)",
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
      onClick={onCancel}
    >
      <div
        className="card"
        style={{ maxWidth: 480, width: "100%", padding: 24, border: "1px solid var(--bad)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 10 }}>
          ⚠️ Confirm live trading on &quot;{strategyName}&quot;
        </div>
        <ul style={{ fontSize: 13, color: "var(--muted)", paddingLeft: 18, marginBottom: 16 }}>
          <li style={{ marginBottom: 6 }}>This will send live trading signals to your real, connected MT5 account.</li>
          <li style={{ marginBottom: 6 }}>Trades will be executed automatically on your account.</li>
          <li>This carries real financial risk.</li>
        </ul>
        {error ? (
          <p style={{ color: "var(--bad)", marginBottom: 12 }} role="alert">
            {error}
          </p>
        ) : null}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            style={{ background: "var(--bad)", color: "#1a0508" }}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Starting..." : "I understand - Start live trading"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function StrategySetupWizard({
  strategy,
  assignment,
  mt5Connection,
  liveBalance,
  onClose,
}: {
  strategy: StrategyView;
  assignment: MyAssignmentView;
  mt5Connection: Mt5ConnectionView | null;
  liveBalance: LiveBalance;
  onClose: () => void;
}) {
  const strategyName = strategy.name;
  const router = useRouter();
  const [multiplier, setMultiplier] = useState<number>(Number(assignment.multiplier) || 1);
  const [previewLot, setPreviewLot] = useState<string | null>(assignment.effective_lot);
  const [sizingBusy, setSizingBusy] = useState(false);
  const [sizingError, setSizingError] = useState<string | null>(null);
  const [showMt5Modal, setShowMt5Modal] = useState(false);
  const [showRiskModal, setShowRiskModal] = useState(false);
  const [startBusy, setStartBusy] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const connected = mt5Connection?.status === "CONNECTED";
  const belowMinBalance =
    strategy.min_balance !== null &&
    liveBalance.available &&
    liveBalance.balance !== undefined &&
    liveBalance.balance < Number(strategy.min_balance);
  // What actually gets used - the slider spans 1X-100X, but the backend
  // still clamps to the admin-granted range per assignment, so the
  // equation must show that clamp too or the math looks broken (e.g.
  // "0.10L x 100X = 0.30 Lots").
  const effectiveMultiplier = Math.min(
    Number(assignment.multiplier_max),
    Math.max(Number(assignment.multiplier_min), multiplier),
  );
  const multiplierCapped = effectiveMultiplier !== multiplier;

  useEffect(() => {
    let cancelled = false;
    void fetch("/api/me/assignments/preview-lot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        master_lot: assignment.master_lot,
        multiplier,
        multiplier_min: assignment.multiplier_min,
        multiplier_max: assignment.multiplier_max,
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
  }, [assignment.master_lot, assignment.multiplier_min, assignment.multiplier_max, multiplier]);

  async function saveSizing() {
    setSizingBusy(true);
    setSizingError(null);
    const res = await fetch(`/api/me/assignments/${assignment.id}/multiplier`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ multiplier }),
    });
    setSizingBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setSizingError(body.detail ?? `save failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  async function confirmStart() {
    setStartBusy(true);
    setStartError(null);
    const res = await fetch(`/api/me/assignments/${assignment.id}/confirm-start`, {
      method: "POST",
    });
    setStartBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setStartError(body.detail ?? `couldn't start (${res.status})`);
      return;
    }
    setShowRiskModal(false);
    router.refresh();
    onClose();
  }

  const sizingChanged = multiplier !== Number(assignment.multiplier);

  return (
    <>
      <div
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(4,6,10,0.7)",
          zIndex: 100,
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "center",
          padding: "40px 20px",
          overflowY: "auto",
        }}
        onClick={onClose}
      >
        <div
          className="card"
          style={{ maxWidth: 620, width: "100%", padding: 24 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 800 }}>Setup Wizard</div>
              <div style={{ color: "var(--muted)", fontSize: 12.5 }}>{strategyName}</div>
            </div>
            <button className="secondary" onClick={onClose} style={{ padding: "4px 10px" }}>
              ✕
            </button>
          </div>

          <div className="card" style={{ marginTop: 20, marginBottom: 14 }}>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 10 }}>Step 1 — Lot sizing</div>
            <MultiplierSlider value={multiplier} onChange={setMultiplier} />
            {multiplierCapped ? (
              <WarningBanner
                tone="warn"
                title={`Capped to ${effectiveMultiplier}X`}
                message={`Your account is entitled to ${assignment.multiplier_min}X-${assignment.multiplier_max}X on this strategy - ${multiplier}X will be capped to ${effectiveMultiplier}X. Ask an admin to raise your limit for more.`}
              />
            ) : null}
            <div className="stat-sub" style={{ marginBottom: 10 }}>
              <span>Projected execution lot</span>
              <span style={{ color: "var(--fg)", fontWeight: 700 }}>
                {assignment.master_lot}L × {effectiveMultiplier}X ={" "}
                {previewLot !== null ? `${previewLot} Lots` : "—"}
              </span>
            </div>
            {sizingError ? (
              <p style={{ color: "var(--bad)", fontSize: 12, marginBottom: 8 }} role="alert">
                {sizingError}
              </p>
            ) : null}
            <button
              type="button"
              className="secondary"
              disabled={!sizingChanged || sizingBusy}
              onClick={() => void saveSizing()}
            >
              {sizingBusy ? "Saving..." : `Save ${multiplier}X sizing`}
            </button>
          </div>

          <div className="card" style={{ marginBottom: 14 }}>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 10 }}>
              Step 2 — Connect MT5 account
            </div>
            {strategy.min_balance ? (
              <WarningBanner
                tone={belowMinBalance ? "bad" : "warn"}
                title={
                  belowMinBalance
                    ? "Connected account is below the minimum"
                    : `Minimum balance required: $${strategy.min_balance}`
                }
                message={
                  belowMinBalance
                    ? `"${strategyName}" requires $${strategy.min_balance}, but your connected account's balance is $${liveBalance.balance?.toFixed(2)} - fund it before continuing.`
                    : `"${strategyName}" requires a minimum MT5 account balance of $${strategy.min_balance} to work correctly - make sure the account you connect meets this.`
                }
                style={{ marginBottom: 14 }}
              />
            ) : null}
            {connected ? (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <p style={{ color: "var(--ok)", fontSize: 13, margin: 0 }}>
                  ✅ Connection successful — {mt5Connection?.broker_server} ({mt5Connection?.login})
                </p>
                <button type="button" className="secondary" onClick={() => setShowMt5Modal(true)}>
                  Manage / Disconnect
                </button>
              </div>
            ) : (
              <>
                <p style={{ color: "var(--muted)", fontSize: 12.5, marginBottom: 10 }}>
                  {mt5Connection
                    ? `❌ Not connected yet (status: ${mt5Connection.status}). Finish connecting to proceed.`
                    : "Connect your MT5 account - your broker server, login, and password are sent directly to MetaApi to set up your trading connection."}
                </p>
                <button type="button" className="secondary" onClick={() => setShowMt5Modal(true)}>
                  Connect MT5 Account
                </button>
              </>
            )}
          </div>

          <div className="card">
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 10 }}>
              Step 3 — Start / go-live confirmation
            </div>
            {belowMinBalance ? (
              <WarningBanner
                tone="bad"
                title="Can't start yet"
                message={`Your MT5 account balance ($${liveBalance.balance?.toFixed(2)}) is below the $${strategy.min_balance} this strategy requires - fund your account before starting.`}
              />
            ) : (
              <p style={{ color: "var(--muted)", fontSize: 12.5, marginBottom: 12 }}>
                {!connected
                  ? "Complete Step 2 first - Start is only available once your MT5 account is connected."
                  : "Once you confirm, real-time alerts for this strategy will route to your MT5 account."}
              </p>
            )}
            <button
              type="button"
              className="btn-primary"
              disabled={!connected || belowMinBalance}
              title={belowMinBalance ? "Fund your MT5 account to meet the minimum balance first" : undefined}
              onClick={() => setShowRiskModal(true)}
            >
              🚀 Start
            </button>
          </div>
        </div>
      </div>

      {showMt5Modal ? (
        <Mt5ConnectionModal
          connection={mt5Connection}
          displayName={strategyName}
          minBalance={strategy.min_balance}
          onClose={() => {
            setShowMt5Modal(false);
            router.refresh();
          }}
        />
      ) : null}

      {showRiskModal ? (
        <RiskConfirmModal
          strategyName={strategyName}
          busy={startBusy}
          error={startError}
          onConfirm={() => void confirmStart()}
          onCancel={() => setShowRiskModal(false)}
        />
      ) : null}
    </>
  );
}
