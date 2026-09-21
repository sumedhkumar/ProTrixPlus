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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metaApiLink, setMetaApiLink] = useState<string | null>(null);
  const [linking, setLinking] = useState(false);
  const [checking, setChecking] = useState(false);

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
    setBusy(true);
    setError(null);
    const res = await fetch("/api/me/mt5-connection", { method: "DELETE" });
    setBusy(false);
    if (!res.ok && res.status !== 404) {
      setError(`disconnect failed (${res.status})`);
      return;
    }
    setMetaApiLink(null);
    router.refresh();
    onClose();
  }

  async function startMetaApiLink() {
    setLinking(true);
    setError(null);
    const res = await fetch("/api/me/mt5-connection/metaapi-link", { method: "POST" });
    setLinking(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `couldn't start MetaApi setup (${res.status})`);
      return;
    }
    const body = (await res.json()) as { configuration_link: string };
    setMetaApiLink(body.configuration_link);
    router.refresh();
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
                  style={{ background: "var(--bad)", color: "#1a0508" }}
                  disabled={busy}
                  onClick={() => void disconnect()}
                >
                  Disconnect
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
              <p style={{ color: "var(--dim)", fontSize: 11.5, marginBottom: 16 }}>
                No password field here on purpose — you&apos;ll enter that directly with MetaApi in
                the next step, never with ProTrixPlus.
              </p>

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
                🔐 Connect via MetaApi (real, self-service)
              </div>
              {!connection ? (
                <p style={{ color: "var(--muted)", fontSize: 12.5 }}>
                  Save your broker server above first.
                </p>
              ) : metaApiLink ? (
                <>
                  <p style={{ color: "var(--muted)", fontSize: 12.5, marginBottom: 10 }}>
                    Open this link and enter your MT5 login and password directly with MetaApi —
                    ProTrixPlus never sees it.
                  </p>
                  <a
                    href={metaApiLink}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-primary"
                    style={{ display: "inline-block", marginBottom: 10, textDecoration: "none" }}
                  >
                    Open secure MetaApi setup →
                  </a>
                  <div>
                    <button
                      type="button"
                      className="secondary"
                      disabled={checking}
                      onClick={() => void checkStatus()}
                    >
                      {checking ? "Checking..." : "I've finished — check status"}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p style={{ color: "var(--muted)", fontSize: 12.5, marginBottom: 10 }}>
                    {connection.metaapi_account_id
                      ? "A MetaApi account is already attached. Generate a fresh link if you need to re-enter your password."
                      : "Generates a real MetaApi setup link — no password typed here or seen by an admin."}
                  </p>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={linking}
                    onClick={() => void startMetaApiLink()}
                  >
                    {linking ? "Generating..." : "⚡ Connect via MetaApi"}
                  </button>
                </>
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
                Your broker server and login are saved with ProTrixPlus; your password is entered
                directly with MetaApi via the &quot;Connect via MetaApi&quot; link, and never passes
                through ProTrixPlus or an admin.
              </p>
            </div>
            <div className="card" style={{ textAlign: "left" }}>
              <strong style={{ display: "block", marginBottom: 6 }}>This is real and live</strong>
              <p style={{ color: "var(--muted)", fontSize: 12.5 }}>
                Clicking &quot;Connect via MetaApi&quot; creates a real MetaApi account (with no
                password) and a real, MetaApi-hosted link. Once you finish entering your credentials
                there, click &quot;I&apos;ve finished — check status&quot; here to confirm the real
                connection.
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
  );
}
