"use client";

import { useState } from "react";

import type { StrategyView } from "@/lib/api";

type Action = "BUY" | "SELL" | "CLOSE";

function randomAlertId(symbol: string): string {
  return `TV_ALT_${symbol || "SIG"}_${Math.floor(Math.random() * 90000 + 10000)}`;
}

// Static illustrative risk-check figures - there is no real market-data feed
// or AI model behind these. Always shown with a DEMO badge, never wired to
// the actual dispatch decision.
const PRE_FLIGHT = {
  slippage: "+0.35 pips",
  liquidity: "94 / 100",
  news: "Clear (Low Risk)",
  conviction: "92% Optimal",
};

export function SimulateSignalModal({
  strategies,
  onClose,
}: {
  strategies: StrategyView[];
  onClose: () => void;
}) {
  const activeStrategies = strategies.filter((s) => s.is_active);
  const [strategyId, setStrategyId] = useState(activeStrategies[0]?.id ?? "");
  const [action, setAction] = useState<Action>("BUY");
  const [price, setPrice] = useState("2648.50");
  const strategy = strategies.find((s) => s.id === strategyId);
  const [alertId, setAlertId] = useState(() => randomAlertId(strategy?.symbol ?? "SIG"));
  const [tampered, setTampered] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [lastEnvelope, setLastEnvelope] = useState<Record<string, unknown> | null>(null);

  function regenId() {
    setAlertId(randomAlertId(strategy?.symbol ?? "SIG"));
  }

  // `exactRepeat`: for the duplicate test, resend the identical previously-
  // sent envelope (idempotency is keyed on the whole payload hash, not just
  // signal_id - reusing the id with a fresh timestamp would be a real
  // conflict, not a duplicate).
  async function dispatch(exactRepeat?: Record<string, unknown>) {
    if (!strategy && !exactRepeat) return;
    setBusy(true);
    setResult(null);
    const payload =
      exactRepeat ?? {
        strategy_key: strategy!.strategy_key,
        strategy_version: strategy!.strategy_version,
        symbol: strategy!.symbol ?? "EURUSD",
        timeframe: strategy!.timeframe ?? "15m",
        action,
        signal_id: alertId,
        tamper_secret: tampered,
      };
    const res = await fetch("/api/simulate-signal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = (await res.json().catch(() => ({}))) as {
      duplicate?: boolean;
      detail?: string | { errors?: string[] };
      error?: string;
      sent_envelope?: Record<string, unknown>;
    };
    setBusy(false);
    if (res.status === 401) {
      setResult({ ok: false, text: "401 Unauthorized - tampered secret correctly rejected" });
      return;
    }
    if (!res.ok) {
      const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body.error);
      setResult({ ok: false, text: `${res.status} - ${detail}` });
      return;
    }
    if (body.sent_envelope) setLastEnvelope(body.sent_envelope);
    setResult({
      ok: true,
      text: body.duplicate
        ? "200 - duplicate (identical payload, correctly deduped)"
        : "202 - accepted and fanned out to eligible clients",
    });
  }

  async function copyCurl() {
    if (!strategy) return;
    const curl = `curl -X POST http://localhost:8000/webhook/tradingview \\
  -H "Content-Type: application/json" \\
  -H "X-Webhook-Token: <your-webhook-secret>" \\
  -d '{
    "schema_version": "1.0",
    "strategy_key": "${strategy.strategy_key}",
    "strategy_version": "${strategy.strategy_version}",
    "signal_id": "${alertId}",
    "event_time_utc": "2026-09-18T00:00:00Z",
    "action": "${action}",
    "symbol": "${strategy.symbol ?? "EURUSD"}",
    "timeframe": "${strategy.timeframe ?? "15m"}"
  }'`;
    try {
      await navigator.clipboard.writeText(curl);
      setResult({ ok: true, text: "curl command copied to clipboard" });
    } catch {
      setResult({ ok: false, text: "clipboard access denied by browser" });
    }
  }

  return (
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
        style={{ maxWidth: 680, width: "100%", padding: 24 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 17, fontWeight: 800, display: "flex", alignItems: "center", gap: 10 }}>
              TradingView Webhook Gateway Simulator
              <span className="badge-pill badge-blue">Live Fan-Out Engine</span>
            </div>
            <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 6, maxWidth: 480 }}>
              Dispatches a real signal through the real webhook - not a mock. Verifies idempotency,
              entitlement-gated fan-out, and (once MetaApi is wired in) MT5 bridge dispatch.
            </p>
          </div>
          <button className="secondary" onClick={onClose} style={{ padding: "4px 10px" }}>
            ✕
          </button>
        </div>

        {activeStrategies.length === 0 ? (
          <div className="pending-panel" style={{ marginTop: 16 }}>
            No active strategies to simulate against - create or turn one ON first.
          </div>
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 20 }}>
              <div>
                <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
                  Target strategy
                </label>
                <select
                  value={strategyId}
                  onChange={(e) => {
                    setStrategyId(e.target.value);
                    setResult(null);
                  }}
                  style={{ width: "100%" }}
                >
                  {activeStrategies.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.symbol ?? "no symbol"} - ACTIVE)
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
                  Order action
                </label>
                <div style={{ display: "flex", gap: 6 }}>
                  {(["BUY", "SELL", "CLOSE"] as const).map((a) => (
                    <button
                      key={a}
                      type="button"
                      className={action === a ? "" : "secondary"}
                      style={{
                        flex: 1,
                        background:
                          action === a
                            ? a === "BUY"
                              ? "var(--ok)"
                              : a === "SELL"
                                ? "var(--bad)"
                                : "var(--accent-purple)"
                            : undefined,
                        color: action === a ? "#05070d" : undefined,
                      }}
                      onClick={() => setAction(a)}
                    >
                      {a}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
                  Signal price ({strategy?.symbol ?? "n/a"})
                </label>
                <input value={price} onChange={(e) => setPrice(e.target.value)} style={{ width: "100%" }} />
                <span style={{ fontSize: 11, color: "var(--dim)" }}>Illustrative - not sent in the payload</span>
              </div>
              <div>
                <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
                  Alert ID (idempotency key)
                </label>
                <div style={{ display: "flex", gap: 8 }}>
                  <input value={alertId} onChange={(e) => setAlertId(e.target.value)} style={{ flex: 1 }} />
                  <button type="button" className="secondary" onClick={regenId}>
                    ↻
                  </button>
                </div>
              </div>
            </div>

            <div className="card" style={{ marginTop: 16, padding: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="card-title">Webhook secret</span>
                <button
                  type="button"
                  className={tampered ? "" : "secondary"}
                  style={{ background: tampered ? "var(--bad)" : undefined, fontSize: 12, padding: "4px 10px" }}
                  onClick={() => setTampered((v) => !v)}
                >
                  {tampered ? "Tampered (will 401)" : "Tamper secret (test 401)"}
                </button>
              </div>
              <input readOnly value="••••••••••••••••" style={{ width: "100%", marginTop: 8 }} />
              <span style={{ fontSize: 11, color: "var(--dim)" }}>
                Managed server-side - the real secret is never sent to your browser.
              </span>
            </div>

            <div className="card" style={{ marginTop: 16, padding: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span className="card-title">ProTrix AI Pre-Flight Guard</span>
                <span className="badge-pill badge-demo">DEMO</span>
              </div>
              <div className="stat-sub-cols">
                <div>
                  <div style={{ color: "var(--ok)" }}>{PRE_FLIGHT.slippage}</div>
                  <div>Predicted slippage</div>
                </div>
                <div>
                  <div>{PRE_FLIGHT.liquidity}</div>
                  <div>Liquidity depth</div>
                </div>
                <div>
                  <div>{PRE_FLIGHT.news}</div>
                  <div>High-impact news</div>
                </div>
                <div>
                  <div>{PRE_FLIGHT.conviction}</div>
                  <div>AI conviction</div>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
              <button
                type="button"
                className="secondary"
                disabled={!lastEnvelope || busy}
                title={lastEnvelope ? "Resend the identical last payload" : "Dispatch once first"}
                onClick={() => lastEnvelope && void dispatch(lastEnvelope)}
              >
                Test duplicate signal (real dedup)
              </button>
              <button type="button" className="secondary" onClick={() => void copyCurl()}>
                Copy curl
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={busy}
                style={{ marginLeft: "auto" }}
                onClick={() => void dispatch()}
              >
                {busy ? "Dispatching..." : "Dispatch signal to gateway"}
              </button>
            </div>

            {result ? (
              <p style={{ marginTop: 12, color: result.ok ? "var(--ok)" : "var(--bad)", fontSize: 13 }}>
                {result.text}
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
