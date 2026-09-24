"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AlertView, StrategyView } from "@/lib/api";

export function AdminStrategyCatalog({
  strategies,
  alerts,
  canEdit,
}: {
  strategies: StrategyView[];
  alerts: AlertView[];
  /** STRATEGY_ADMIN/SUPER_ADMIN can create/toggle/bundle; everyone else views read-only. */
  canEdit: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alertConfigFor, setAlertConfigFor] = useState<string | null>(null);
  const [alertConfigBody, setAlertConfigBody] = useState<string>("");
  const [bundleFor, setBundleFor] = useState<string | null>(null);
  const [selectedAlertIds, setSelectedAlertIds] = useState<string[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [form, setForm] = useState({
    strategy_key: "",
    strategy_version: "1.0",
    name: "",
    description: "",
    symbol: "",
    timeframe: "",
    price: "",
    profit_share_percent: "",
    base_lot: "",
    win_rate: "",
    max_drawdown: "",
    description_short: "",
    min_balance: "",
  });

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/admin/strategies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        strategy_key: form.strategy_key,
        strategy_version: form.strategy_version,
        name: form.name,
        description: form.description || null,
        symbol: form.symbol || null,
        timeframe: form.timeframe || null,
        price: form.price || null,
        profit_share_percent: form.profit_share_percent || null,
        base_lot: form.base_lot || null,
        win_rate: form.win_rate || null,
        max_drawdown: form.max_drawdown || null,
        description_short: form.description_short || null,
        min_balance: form.min_balance || null,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `create failed (${res.status})`);
      return;
    }
    setForm({
      strategy_key: "",
      strategy_version: "1.0",
      name: "",
      description: "",
      symbol: "",
      timeframe: "",
      price: "",
      profit_share_percent: "",
      base_lot: "",
      win_rate: "",
      max_drawdown: "",
      description_short: "",
      min_balance: "",
    });
    setShowCreateModal(false);
    router.refresh();
  }

  async function toggle(id: string, isActive: boolean) {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/admin/strategies/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !isActive }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `toggle failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  async function viewAlertConfig(id: string) {
    setAlertConfigFor(id);
    setAlertConfigBody("loading...");
    const res = await fetch(`/api/admin/strategies/${id}/alert-config`);
    const body = await res.json();
    setAlertConfigBody(JSON.stringify(body, null, 2));
  }

  function openBundle(strategyId: string) {
    setBundleFor(strategyId);
    setSelectedAlertIds(alerts.filter((a) => a.strategy_id === strategyId).map((a) => a.id));
  }

  async function saveBundle(strategyId: string) {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/admin/strategies/${strategyId}/alerts`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alert_ids: selectedAlertIds }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `bundle failed (${res.status})`);
      return;
    }
    setBundleFor(null);
    router.refresh();
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Strategy Lifecycle &amp; Catalog Management</span>
        {canEdit ? (
          <button type="button" className="btn-primary" onClick={() => setShowCreateModal(true)}>
            + Create Strategy
          </button>
        ) : null}
      </div>
      <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: -6, marginBottom: 14 }}>
        New strategies are created hidden from clients. Set a price and profit-share %, then click
        &quot;Approve &amp; Enable&quot; to make it visible in the Strategy Marketplace.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table data-testid="admin-strategy-catalog">
          <thead>
            <tr>
              <th>Strategy &amp; symbol</th>
              <th>Timeframe</th>
              <th>Base lot</th>
              <th>Min. balance</th>
              <th>Pricing &amp; split</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((s) => (
              <tr key={s.id}>
                <td>
                  <div style={{ fontWeight: 700 }}>
                    {s.name} {s.symbol ? <span className="badge-pill badge-neutral">{s.symbol}</span> : null}
                  </div>
                  <code>
                    {s.strategy_key}@{s.strategy_version}
                  </code>
                </td>
                <td>{s.timeframe ?? "-"}</td>
                <td>{s.base_lot ?? "-"}</td>
                <td>{s.min_balance ? `$${s.min_balance}` : "-"}</td>
                <td>
                  {s.price ? `$${s.price}/mo` : "-"}
                  {s.profit_share_percent ? (
                    <div style={{ color: "var(--muted)", fontSize: 11 }}>
                      {s.profit_share_percent}% profit-share
                    </div>
                  ) : null}
                </td>
                <td>
                  <span className={`badge-pill ${s.is_active ? "badge-green" : "badge-neutral"}`}>
                    {s.is_active ? "ACTIVE - visible to clients" : "NOT ENABLED"}
                  </span>
                </td>
                <td>
                  {(() => {
                    const unpriced = s.price === null || s.profit_share_percent === null;
                    const blockedByPricing = !s.is_active && unpriced;
                    return (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <div style={{ display: "flex", gap: 6 }}>
                          {canEdit ? (
                            <button
                              className="secondary"
                              disabled={busy || blockedByPricing}
                              title={
                                blockedByPricing
                                  ? "Set a price and profit-share % (below) before approving this strategy for clients"
                                  : undefined
                              }
                              onClick={() => void toggle(s.id, s.is_active)}
                            >
                              {s.is_active ? "Turn OFF" : "Approve & Enable"}
                            </button>
                          ) : null}
                          <button className="secondary" onClick={() => void viewAlertConfig(s.id)}>
                            Alert config
                          </button>
                          {canEdit ? (
                            <button className="secondary" onClick={() => openBundle(s.id)}>
                              Bundle alerts
                            </button>
                          ) : null}
                        </div>
                        {blockedByPricing ? (
                          <span style={{ fontSize: 11, color: "var(--dim)" }}>
                            Set price &amp; profit-share to enable
                          </span>
                        ) : null}
                      </div>
                    );
                  })()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {alertConfigFor ? (
        <div className="pending-panel" style={{ textAlign: "left", marginTop: 14 }}>
          <strong>TradingView alert config</strong>
          <pre style={{ overflowX: "auto", fontSize: 12 }}>{alertConfigBody}</pre>
          <button className="secondary" onClick={() => setAlertConfigFor(null)}>
            Close
          </button>
        </div>
      ) : null}

      {bundleFor ? (
        <div className="pending-panel" style={{ textAlign: "left", marginTop: 14 }}>
          <strong>Bundle alerts into this strategy</strong>
          <p style={{ color: "var(--muted)", fontSize: 12 }}>
            Select the alerts that belong to this strategy&apos;s catalog card. This is
            documentation/display only - it never changes how an incoming signal is matched.
          </p>
          {alerts.length === 0 ? (
            <p style={{ color: "var(--dim)", fontSize: 12 }}>
              No alerts in the catalog yet - create one in the Alert Catalog tab first.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
              {alerts.map((a) => (
                <label key={a.id} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={selectedAlertIds.includes(a.id)}
                    onChange={(e) =>
                      setSelectedAlertIds((prev) =>
                        e.target.checked ? [...prev, a.id] : prev.filter((id) => id !== a.id),
                      )
                    }
                  />
                  {a.name} — {a.symbol} @ {a.timeframe}
                  {a.strategy_id && a.strategy_id !== bundleFor ? (
                    <span style={{ color: "var(--dim)", fontSize: 11 }}>(bundled elsewhere)</span>
                  ) : null}
                </label>
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="secondary" onClick={() => setBundleFor(null)} disabled={busy}>
              Cancel
            </button>
            <button onClick={() => void saveBundle(bundleFor)} disabled={busy}>
              {busy ? "Saving..." : "Save bundle"}
            </button>
          </div>
        </div>
      ) : null}

      {error ? (
        <p style={{ color: "var(--bad)", marginTop: 12 }} role="alert">
          {error}
        </p>
      ) : null}

      {showCreateModal ? (
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
          onClick={() => setShowCreateModal(false)}
        >
          <div
            className="card"
            style={{ maxWidth: 520, width: "100%", padding: 24 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <span style={{ fontSize: 16, fontWeight: 800 }}>Create Strategy</span>
              <button
                type="button"
                className="secondary"
                onClick={() => setShowCreateModal(false)}
                style={{ padding: "4px 10px" }}
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={(e) => void create(e)}
              style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 18 }}
            >
              <input
                placeholder="strategy_key"
                value={form.strategy_key}
                onChange={(e) => setForm({ ...form, strategy_key: e.target.value })}
                required
              />
              <input
                placeholder="strategy_version"
                value={form.strategy_version}
                onChange={(e) => setForm({ ...form, strategy_version: e.target.value })}
                required
              />
              <input
                placeholder="name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
              <input
                placeholder="symbol (e.g. XAUUSD)"
                value={form.symbol}
                onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
              />
              <input
                placeholder="timeframe (e.g. 1h)"
                value={form.timeframe}
                onChange={(e) => setForm({ ...form, timeframe: e.target.value })}
              />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <input
                  placeholder="price"
                  value={form.price}
                  onChange={(e) => setForm({ ...form, price: e.target.value })}
                />
                <input
                  placeholder="profit share %"
                  value={form.profit_share_percent}
                  onChange={(e) => setForm({ ...form, profit_share_percent: e.target.value })}
                />
              </div>
              <input
                placeholder="base lot"
                value={form.base_lot}
                onChange={(e) => setForm({ ...form, base_lot: e.target.value })}
              />
              <input
                placeholder="minimum MT5 account balance required (e.g. 500)"
                value={form.min_balance}
                onChange={(e) => setForm({ ...form, min_balance: e.target.value })}
              />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <input
                  placeholder="win rate % (e.g. 62)"
                  value={form.win_rate}
                  onChange={(e) => setForm({ ...form, win_rate: e.target.value })}
                />
                <input
                  placeholder="max drawdown % (e.g. 12)"
                  value={form.max_drawdown}
                  onChange={(e) => setForm({ ...form, max_drawdown: e.target.value })}
                />
              </div>
              <input
                placeholder="short description (one-liner)"
                value={form.description_short}
                onChange={(e) => setForm({ ...form, description_short: e.target.value })}
              />
              <textarea
                placeholder="long description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={3}
              />
              {error ? (
                <p style={{ color: "var(--bad)" }} role="alert">
                  {error}
                </p>
              ) : null}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 6 }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={busy}>
                  {busy ? "Creating..." : "Create strategy"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
