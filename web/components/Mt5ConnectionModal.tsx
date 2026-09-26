"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Mt5ConnectionView } from "@/lib/api";

import { WarningBanner } from "./WarningBanner";

type Tab = "setup" | "instructions";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Second, explicit confirmation before the account-creation call actually
 * fires - the checkbox above is easy to click without reading; this forces
 * a distinct, deliberate "yes" so a client can't create a chargeable
 * MetaApi account by accident. Mirrors StrategySetupWizard's
 * RiskConfirmModal pattern used for the "go live" confirmation. */
function ChargeConfirmModal({
  busy,
  onConfirm,
  onCancel,
}: {
  busy: boolean;
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
        style={{ maxWidth: 460, width: "100%", padding: 24, border: "1px solid var(--warn)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 10 }}>
          💳 Confirm: this creates a chargeable account
        </div>
        <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 16 }}>
          Connecting this broker login provisions a real MetaApi trading account. This is a real,
          separately-billed resource - not a free/demo simulation. Only continue if you intend to
          connect this account now.
        </p>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={onConfirm}
            disabled={busy}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            {busy ? (
              <>
                <span className="spinner" /> Connecting...
              </>
            ) : (
              "Yes, create this chargeable account"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// Deploying/redeploying an account genuinely takes a few seconds beyond the
// initial connect call returning (MetaApi still has to finish the real
// broker handshake) - poll instead of trusting the very first status.
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 20; // ~40s ceiling before giving up honestly

export function Mt5ConnectionModal({
  connection,
  displayName,
  minBalance,
  onClose,
}: {
  connection: Mt5ConnectionView | null;
  displayName: string;
  minBalance?: string | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("setup");
  const [broker, setBroker] = useState(connection?.broker_server ?? "");
  const [login, setLogin] = useState(connection?.login ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showChargeConfirm, setShowChargeConfirm] = useState(false);
  const [checkingNewAccount, setCheckingNewAccount] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [checking, setChecking] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  // Set only while actively polling after a connect attempt - separate from
  // `connecting` (the initial POST) so the button/spinner can say something
  // more honest than just "Connecting..." once that first call is done and
  // we're now waiting to confirm the broker handshake actually completed.
  const [pollingStatus, setPollingStatus] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/me/mt5-connection", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ broker_server: broker, login }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(`save failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  async function disconnect() {
    setDisconnecting(true);
    setError(null);
    const res = await fetch("/api/me/mt5-connection", { method: "DELETE" });
    setDisconnecting(false);
    if (!res.ok && res.status !== 404) {
      setError(`disconnect failed (${res.status})`);
      return;
    }
    router.refresh();
    onClose();
  }

  /** Polls real connection status after a connect attempt until it's
   * actually CONNECTED (or a terminal ERROR), rather than trusting the
   * very first response - deploying/redeploying an account genuinely
   * takes a few seconds beyond that first call returning. Gives up
   * honestly after POLL_MAX_ATTEMPTS rather than spinning forever. */
  async function pollUntilConnected(initialStatus: string) {
    let status = initialStatus;
    setPollingStatus(status);
    let attempt = 0;
    while (attempt < POLL_MAX_ATTEMPTS && status !== "CONNECTED" && status !== "ERROR") {
      attempt += 1;
      await sleep(POLL_INTERVAL_MS);
      const res = await fetch("/api/me/mt5-connection/check", { method: "POST" });
      if (!res.ok) break;
      const body = (await res.json()) as Mt5ConnectionView;
      status = body.status;
      setPollingStatus(status);
    }
    setPollingStatus(null);
    router.refresh();
  }

  async function requestConnect(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setCheckingNewAccount(true);
    const res = await fetch("/api/me/mt5-connection/would-create-new-account", {
      method: "POST",
    });
    setCheckingNewAccount(false);
    if (res.ok) {
      const body = (await res.json()) as { will_create_new_account: boolean };
      if (body.will_create_new_account) {
        setShowChargeConfirm(true);
        return;
      }
      // Reusing an already-provisioned account - not a new charge, so skip
      // the confirmation dialog and connect straight away.
      await connectWithCredentials();
      return;
    }
    // Couldn't tell in advance (e.g. MetaApi unreachable) - fall through to
    // the real connect call, which will surface its own honest error.
    await connectWithCredentials();
  }

  async function connectWithCredentials() {
    setConnecting(true);
    setError(null);
    const res = await fetch("/api/me/mt5-connection/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // By the time this fires, requestConnect has already established
      // (via would-create-new-account) that either no new account is being
      // created, or the client explicitly confirmed the charge dialog -
      // the server enforces this same rule independently either way.
      body: JSON.stringify({ password, confirm_charge: true }),
    });
    setConnecting(false);
    setShowChargeConfirm(false);
    setPassword("");
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `couldn't connect (${res.status})`);
      return;
    }
    const body = (await res.json()) as Mt5ConnectionView;
    await pollUntilConnected(body.status);
  }

  async function checkStatus() {
    setChecking(true);
    setError(null);
    const res = await fetch("/api/me/mt5-connection/check", { method: "POST" });
    setChecking(false);
    if (!res.ok) {
      setError(`check failed (${res.status})`);
      return;
    }
    router.refresh();
  }

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
          <div style={{ display: "flex", gap: 12 }}>
            <div className="icon-badge teal">🖧</div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 800 }}>MetaTrader 5 Account Bridge</div>
              <div style={{ color: "var(--muted)", fontSize: 12.5 }}>Client: {displayName}</div>
            </div>
          </div>
          <button className="secondary" onClick={onClose} style={{ padding: "4px 10px" }}>
            ✕
          </button>
        </div>

        <div style={{ display: "flex", gap: 4, marginTop: 18, borderBottom: "1px solid var(--panel-border)" }}>
          <button
            type="button"
            className="tab-link"
            style={tab === "setup" ? { color: "var(--fg)", borderBottomColor: "var(--accent-blue)" } : undefined}
            onClick={() => setTab("setup")}
          >
            Connection Setup
          </button>
          <button
            type="button"
            className="tab-link"
            style={tab === "instructions" ? { color: "var(--fg)", borderBottomColor: "var(--accent-blue)" } : undefined}
            onClick={() => setTab("instructions")}
          >
            &gt;_ How This Works
          </button>
        </div>

        {tab === "setup" ? (
          <div style={{ marginTop: 20 }}>
            {minBalance ? (
              <WarningBanner
                tone="warn"
                title={`Minimum balance required: $${minBalance}`}
                message="This strategy won't work correctly below that in the MT5 account you connect here."
                style={{ marginBottom: 16 }}
              />
            ) : null}
            {connection ? (
              <div
                className="card"
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 16,
                  padding: "10px 14px",
                }}
              >
                <span style={{ fontSize: 13 }}>
                  Status:{" "}
                  <b style={{ color: connection.status === "CONNECTED" ? "var(--ok)" : "var(--warn)" }}>
                    {connection.status}
                  </b>
                  {connection.last_checked_at ? (
                    <span style={{ color: "var(--dim)" }}>
                      {" "}
                      (checked {new Date(connection.last_checked_at).toLocaleTimeString()})
                    </span>
                  ) : null}
                </span>
                <button
                  type="button"
                  style={{
                    background: "var(--bad)",
                    color: "#1a0508",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                  disabled={disconnecting}
                  onClick={() => void disconnect()}
                >
                  {disconnecting ? (
                    <>
                      <span className="spinner" /> Disconnecting...
                    </>
                  ) : (
                    "Disconnect"
                  )}
                </button>
              </div>
            ) : null}

            <form onSubmit={(e) => void save(e)}>
              <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
                MT5 broker server
              </label>
              <input
                value={broker}
                onChange={(e) => setBroker(e.target.value)}
                placeholder="e.g. ICMarketsSC-Live02"
                required
                style={{ width: "100%", marginBottom: 14 }}
              />

              <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
                MT5 login / account number
              </label>
              <input
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                required
                style={{ width: "100%", marginBottom: 14 }}
              />

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginBottom: 20 }}>
                <button type="submit" className="secondary" disabled={busy}>
                  {busy ? "Saving..." : "Save broker details"}
                </button>
              </div>
            </form>

            <div
              className="card"
              style={{ padding: 16, background: "rgba(124, 108, 246, 0.06)", marginBottom: 16 }}
            >
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>
                🔐 Connect your MT5 account
              </div>
              {!connection ? (
                <p style={{ color: "var(--muted)", fontSize: 12.5 }}>
                  Save your broker server and login above first.
                </p>
              ) : (
                <form onSubmit={requestConnect}>
                  <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
                    MT5 password (master/trading password, not investor/read-only)
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="off"
                    style={{ width: "100%", marginBottom: 8 }}
                  />
                  <p style={{ color: "var(--dim)", fontSize: 11.5, marginBottom: 12 }}>
                    Sent directly to MetaApi.cloud to provision your trading connection - never
                    written to our database or logs, and never seen by an admin.
                  </p>
                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={checkingNewAccount || connecting || pollingStatus !== null}
                      style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                    >
                      {checkingNewAccount ? (
                        <>
                          <span className="spinner" /> Checking account...
                        </>
                      ) : connecting ? (
                        <>
                          <span className="spinner" /> Connecting...
                        </>
                      ) : pollingStatus !== null ? (
                        <>
                          <span className="spinner" /> Confirming connection...
                        </>
                      ) : (
                        "⚡ Connect"
                      )}
                    </button>
                    {connection.metaapi_account_id ? (
                      <button
                        type="button"
                        className="secondary"
                        disabled={checking || pollingStatus !== null}
                        onClick={() => void checkStatus()}
                      >
                        {checking ? "Checking..." : "Check status"}
                      </button>
                    ) : null}
                    {pollingStatus !== null ? (
                      <span style={{ color: "var(--dim)", fontSize: 11.5 }}>
                        Current status: <b>{pollingStatus}</b> - waiting for CONNECTED...
                      </span>
                    ) : null}
                  </div>
                </form>
              )}
            </div>

            {error ? (
              <p style={{ color: "var(--bad)", marginBottom: 12 }} role="alert">
                {error}
              </p>
            ) : null}
          </div>
        ) : (
          <div style={{ marginTop: 20 }}>
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-title" style={{ marginBottom: 8 }}>
                🛡 Real transport: MetaApi.cloud, not a local EA
              </div>
              <p style={{ fontSize: 13, color: "var(--muted)" }}>
                ProTrixPlus&apos;s production transport (ADR-001) is MetaApi.cloud, not a
                locally-installed MT5 Expert Advisor — <strong>no file to download or install</strong>.
                Your broker server, login, and password are submitted here and sent directly to
                MetaApi.cloud to provision your trading connection. Your password is never written
                to our database or logs, and no admin can see it.
              </p>
            </div>
            <div className="card" style={{ textAlign: "left" }}>
              <strong style={{ display: "block", marginBottom: 6 }}>This is real and live</strong>
              <p style={{ color: "var(--muted)", fontSize: 12.5 }}>
                Clicking &quot;Connect&quot; creates a real MetaApi account using the credentials
                you entered and immediately checks its real connection status. Use &quot;Check
                status&quot; if it doesn&apos;t show connected right away - it can take a few
                seconds for MetaApi to establish the link to your broker.
              </p>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
              <button type="button" className="secondary" onClick={() => setTab("setup")}>
                ← Back to connection
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
    {showChargeConfirm ? (
      <ChargeConfirmModal
        busy={connecting}
        onConfirm={() => void connectWithCredentials()}
        onCancel={() => setShowChargeConfirm(false)}
      />
    ) : null}
    </>
  );
}
