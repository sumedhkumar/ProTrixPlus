"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Mt5ConnectionView } from "@/lib/api";

type Tab = "setup" | "instructions";

export function Mt5ConnectionModal({
  connection,
  displayName,
  onClose,
}: {
  connection: Mt5ConnectionView | null;
  displayName: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("setup");
  const [broker, setBroker] = useState(connection?.broker_server ?? "");
  const [login, setLogin] = useState(connection?.login ?? "");
  const [investorToken, setInvestorToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/me/mt5-connection", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ broker_server: broker, login }),
    });
    if (!res.ok) {
      setBusy(false);
      setError(`save failed (${res.status})`);
      return;
    }
    const checkRes = await fetch("/api/me/mt5-connection/check", { method: "POST" });
    setBusy(false);
    if (!checkRes.ok) {
      setError(`connection check failed (${checkRes.status})`);
      return;
    }
    router.refresh();
    onClose();
  }

  async function disconnect() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/me/mt5-connection", { method: "DELETE" });
    setBusy(false);
    if (!res.ok && res.status !== 404) {
      setError(`disconnect failed (${res.status})`);
      return;
    }
    router.refresh();
    onClose();
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
            &gt;_ How This Will Work
          </button>
        </div>

        {tab === "setup" ? (
          <form onSubmit={(e) => void save(e)} style={{ marginTop: 20 }}>
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
                  <b className={connection.status === "CONNECTED" ? "" : undefined} style={{ color: "var(--warn)" }}>
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
                  style={{ background: "var(--bad)", color: "#1a0508" }}
                  disabled={busy}
                  onClick={() => void disconnect()}
                >
                  Disconnect
                </button>
              </div>
            ) : null}

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

            <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
              Investor / EA token authorization
            </label>
            <input
              type="password"
              value={investorToken}
              onChange={(e) => setInvestorToken(e.target.value)}
              placeholder="not yet stored anywhere"
              style={{ width: "100%" }}
            />
            <p style={{ color: "var(--dim)", fontSize: 11.5, marginTop: 6, marginBottom: 20 }}>
              Read-only investor password only - a master trading password should never be entered
              here. <strong>This field isn&apos;t wired to anything yet</strong> - it isn&apos;t
              sent or stored, since the real credential vault (CredentialVault) is still a stub.
              It&apos;ll become real alongside the MetaApi integration.
            </p>

            {error ? (
              <p style={{ color: "var(--bad)", marginBottom: 12 }} role="alert">
                {error}
              </p>
            ) : null}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button type="button" className="secondary" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? "Saving..." : "⚡ Test Connection & Save"}
              </button>
            </div>
          </form>
        ) : (
          <div style={{ marginTop: 20 }}>
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-title" style={{ marginBottom: 8 }}>
                🛡 Real transport: MetaApi.cloud, not a local EA
              </div>
              <p style={{ fontSize: 13, color: "var(--muted)" }}>
                Unlike some bridge tools, ProTrixPlus&apos;s planned production transport
                (ADR-001) is MetaApi.cloud, not a locally-installed MT5 Expert Advisor. That means
                once it&apos;s wired in, there&apos;s <strong>no file to download or install</strong> -
                connecting just needs your broker server, login, and investor password, entered
                above.
              </p>
            </div>
            <div className="pending-panel" style={{ textAlign: "left" }}>
              <strong>Not live yet</strong>
              This deployment has no MetaApi.cloud API key configured, so &ldquo;Test Connection &amp;
              Save&rdquo; stores your details but reports PENDING rather than a real broker check.
              See docs/FULL-BUILD-PLAN.md Phase 3/5.
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
  );
}
