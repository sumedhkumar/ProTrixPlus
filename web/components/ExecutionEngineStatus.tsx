"use client";

import { useRef, useState } from "react";

export interface EngineStats {
  apiHealthy: boolean;
  webhookPath: string;
  idempotencyActive: boolean;
  bridgeLabel: string;
  connectedBridges: number | null;
  totalBridges: number | null;
  totalSignals: number | null;
  signalsHiddenReason: string | null;
}

export function ExecutionEngineStatus({
  stats,
  onTestIngestion,
}: {
  stats: EngineStats;
  onTestIngestion: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function show() {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) setCoords({ top: rect.bottom + 10, left: rect.left });
    setOpen(true);
  }

  function scheduleHide() {
    closeTimer.current = setTimeout(() => setOpen(false), 200);
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="pill"
        style={{ cursor: "pointer" }}
        onMouseEnter={show}
        onMouseLeave={scheduleHide}
        onClick={() => (open ? setOpen(false) : show())}
        title="Click for TradingView Webhook & MT5 Bridge Diagnostics"
      >
        <span className={`dot ${stats.apiHealthy ? "green" : "red"}`} />
        Execution Engine: {stats.apiHealthy ? "Active" : "Unreachable"}
      </button>

      {open ? (
        <div
          role="tooltip"
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            zIndex: 200,
            width: 360,
          }}
          onMouseEnter={show}
          onMouseLeave={scheduleHide}
        >
          <div className="card" style={{ padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span aria-hidden>⚙</span>
                <span style={{ fontWeight: 800, fontSize: 14 }}>ProTrix Execution Engine</span>
              </div>
              <span className={`badge-pill ${stats.apiHealthy ? "badge-green" : "badge-warn"}`}>
                {stats.apiHealthy ? "READY" : "OFFLINE"}
              </span>
            </div>

            <p style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 14, lineHeight: 1.5 }}>
              This engine authenticates the <strong>TradingView Webhook Gateway</strong> and
              dispatches orders to eligible client MT5 accounts.
            </p>

            <div
              style={{
                background: "var(--panel-2, rgba(255,255,255,0.03))",
                border: "1px solid var(--panel-border)",
                borderRadius: 10,
                padding: "10px 12px",
                fontSize: 12,
                display: "grid",
                rowGap: 8,
                marginBottom: 12,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--muted)" }}>Ingestion Webhook:</span>
                <code style={{ color: "var(--accent-blue)" }}>{stats.webhookPath}</code>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--muted)" }}>Idempotency Filter:</span>
                <span style={{ color: "var(--good, #34d399)", fontWeight: 700 }}>
                  {stats.idempotencyActive ? "Active (blocks dupes)" : "Inactive"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--muted)" }}>{stats.bridgeLabel}:</span>
                <span style={{ fontWeight: 700 }}>
                  {stats.connectedBridges === null
                    ? "n/a"
                    : stats.totalBridges !== null
                      ? `${stats.connectedBridges} / ${stats.totalBridges} connected`
                      : stats.connectedBridges > 0
                        ? "Connected"
                        : "Not connected"}
                </span>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>
                {stats.totalSignals === null ? (
                  stats.signalsHiddenReason
                ) : (
                  <>
                    <strong style={{ color: "var(--fg)" }}>{stats.totalSignals}</strong> signals
                    processed
                  </>
                )}
              </span>
              <button
                type="button"
                className="card-link"
                style={{ fontSize: 12 }}
                onClick={() => {
                  setOpen(false);
                  onTestIngestion();
                }}
              >
                Test Ingestion →
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
