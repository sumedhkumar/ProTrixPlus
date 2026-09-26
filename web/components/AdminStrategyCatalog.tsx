"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AlertView, StrategyView, UnmappedSignalStrategyView } from "@/lib/api";

function humanizeStrategyKey(key: string): string {
  return key
    .split(/[-_]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function AdminStrategyCatalog({
  strategies,
  alerts,
  unmappedSignals,
  canEdit,
}: {
  strategies: StrategyView[];
  alerts: AlertView[];
  unmappedSignals: UnmappedSignalStrategyView[];
  /** STRATEGY_ADMIN/SUPER_ADMIN can create/toggle/bundle; everyone else views read-only. */
  canEdit: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alertConfigFor, setAlertConfigFor] = useState<string | null>(null);
  const [alertConfig, setAlertConfig] = useState<{
    webhook_path_template: string;
    alert_message_template: Record<string, unknown>;
    note: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);
  const [bundleFor, setBundleFor] = useState<string | null>(null);
  const [selectedAlertIds, setSelectedAlertIds] = useState<string[]>([]);
  const [pricingEditFor, setPricingEditFor] = useState<string | null>(null);
  const [pricingForm, setPricingForm] = useState({ price: "", profit_share_percent: "" });
  const [pricingBusy, setPricingBusy] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const visibleStrategies = strategies.filter((s) => !s.is_archived);
  const archivedStrategies = strategies.filter((s) => s.is_archived);
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

  async function archive(id: string) {
    if (!window.confirm("Hide this strategy from the admin panel and client marketplace? Its trade history is kept and this is reversible.")) {
      return;
    }
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/admin/strategies/${id}/archive`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `archive failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  async function unarchive(id: string) {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/admin/strategies/${id}/unarchive`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `unarchive failed (${res.status})`);
      return;
    }
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

  function startPricingEdit(s: StrategyView) {
    setPricingEditFor(s.id);
    setPricingForm({ price: s.price ?? "", profit_share_percent: s.profit_share_percent ?? "" });
    setError(null);
  }

  async function savePricing(id: string) {
    if (!pricingForm.price || !pricingForm.profit_share_percent) {
      setError("price and profit-share % are both required");
      return;
    }
    setPricingBusy(true);
    setError(null);
    const res = await fetch(`/api/admin/strategies/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        price: pricingForm.price,
        profit_share_percent: pricingForm.profit_share_percent,
      }),
    });
    setPricingBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `save failed (${res.status})`);
      return;
    }
    setPricingEditFor(null);
    router.refresh();
  }

  async function viewAlertConfig(id: string) {
    setAlertConfigFor(id);
    setAlertConfig(null);
    setCopied(false);
    const res = await fetch(`/api/admin/strategies/${id}/alert-config`);
    const body = (await res.json()) as {
      webhook_path_template: string;
      alert_message_template: Record<string, unknown>;
      note: string;
    };
    setAlertConfig(body);
  }

  async function copyAlertMessage() {
    if (!alertConfig) return;
    await navigator.clipboard.writeText(JSON.stringify(alertConfig.alert_message_template, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
              <th>TradingView</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {visibleStrategies.map((s) => (
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
                  {pricingEditFor === s.id ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 130 }}>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="price ($/mo)"
                        value={pricingForm.price}
                        onChange={(e) => setPricingForm({ ...pricingForm, price: e.target.value })}
                        style={{ fontSize: 12, padding: "4px 6px" }}
                      />
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.01"
                        placeholder="profit-share %"
                        value={pricingForm.profit_share_percent}
                        onChange={(e) =>
                          setPricingForm({ ...pricingForm, profit_share_percent: e.target.value })
                        }
                        style={{ fontSize: 12, padding: "4px 6px" }}
                      />
                      <div style={{ display: "flex", gap: 6 }}>
                        <button
                          className="btn-primary"
                          disabled={pricingBusy}
                          onClick={() => void savePricing(s.id)}
                          style={{ padding: "3px 10px", fontSize: 12 }}
                        >
                          {pricingBusy ? "Saving..." : "Save"}
                        </button>
                        <button
                          className="secondary"
                          disabled={pricingBusy}
                          onClick={() => setPricingEditFor(null)}
                          style={{ padding: "3px 10px", fontSize: 12 }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {s.price ? `$${s.price}/mo` : "-"}
                      {s.profit_share_percent ? (
                        <div style={{ color: "var(--muted)", fontSize: 11 }}>
                          {s.profit_share_percent}% profit-share
                        </div>
                      ) : null}
                      {canEdit ? (
                        <div>
                          <button
                            className="secondary"
                            onClick={() => startPricingEdit(s)}
                            style={{ padding: "2px 8px", fontSize: 11, marginTop: 4 }}
                          >
                            {s.price && s.profit_share_percent ? "Edit price" : "Set price"}
                          </button>
                        </div>
                      ) : null}
                    </>
                  )}
                </td>
                <td>
                  <span className={`badge-pill ${s.is_active ? "badge-green" : "badge-neutral"}`}>
                    {s.is_active ? "ACTIVE - visible to clients" : "NOT ENABLED"}
                  </span>
                </td>
                <td>
                  <span
                    className={`badge-pill ${s.signal_status === "connected" ? "badge-green" : "badge-neutral"}`}
                    title={
                      s.last_signal_at
                        ? `Last signal received: ${new Date(s.last_signal_at).toLocaleString()}`
                        : "No signal ever received from TradingView for this strategy"
                    }
                  >
                    {s.signal_status === "connected" ? "🟢 Connected" : "⚪ Disconnected"}
                  </span>
                  <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 3 }}>
                    {s.last_signal_at ? `last signal ${timeAgo(s.last_signal_at)}` : "no signal yet"}
                  </div>
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
                                  ? "Set a price and profit-share % (use 'Set price' in the Pricing & split column) before approving this strategy for clients"
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
                          {canEdit ? (
                            <button
                              className="secondary"
                              disabled={busy}
                              title="Hide from the admin panel and client marketplace - keeps trade history, reversible"
                              onClick={() => void archive(s.id)}
                            >
                              Archive
                            </button>
                          ) : null}
                        </div>
                        {blockedByPricing ? (
                          <span style={{ fontSize: 11, color: "var(--dim)" }}>
                            Use &quot;Set price&quot; (left) to enable
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

      {archivedStrategies.length > 0 ? (
        <div style={{ marginTop: 14 }}>
          <button
            type="button"
            className="secondary"
            onClick={() => setShowArchived((v) => !v)}
            style={{ fontSize: 12.5 }}
          >
            {showArchived ? "▾" : "▸"} Archived strategies ({archivedStrategies.length})
          </button>
          {showArchived ? (
            <div style={{ overflowX: "auto", marginTop: 10 }}>
              <table>
                <thead>
                  <tr>
                    <th>Strategy &amp; symbol</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {archivedStrategies.map((s) => (
                    <tr key={s.id}>
                      <td>
                        <div style={{ fontWeight: 700 }}>{s.name}</div>
                        <code>
                          {s.strategy_key}@{s.strategy_version}
                        </code>
                      </td>
                      <td>
                        {canEdit ? (
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() => void unarchive(s.id)}
                          >
                            Unarchive
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}

      {alertConfigFor ? (
        <div className="pending-panel" style={{ textAlign: "left", marginTop: 14 }}>
          <strong>TradingView alert config</strong>
          {!alertConfig ? (
            <p style={{ color: "var(--muted)", fontSize: 12.5 }}>Loading...</p>
          ) : (
            <>
              <label
                style={{
                  fontSize: 11.5,
                  color: "var(--muted)",
                  display: "block",
                  marginTop: 12,
                  marginBottom: 4,
                }}
              >
                Webhook URL (replace &lt;your-webhook-secret&gt; with your deployment&apos;s real
                secret)
              </label>
              <code style={{ display: "block", fontSize: 12.5, wordBreak: "break-all" }}>
                {alertConfig.webhook_path_template}
              </code>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginTop: 14,
                  marginBottom: 4,
                }}
              >
                <label style={{ fontSize: 11.5, color: "var(--muted)" }}>
                  Message (paste exactly this into TradingView&apos;s alert Message box)
                </label>
                <button
                  type="button"
                  className="secondary"
                  style={{ padding: "2px 10px", fontSize: 11.5 }}
                  onClick={() => void copyAlertMessage()}
                >
                  {copied ? "Copied!" : "Copy"}
                </button>
              </div>
              <pre
                style={{
                  overflowX: "auto",
                  fontSize: 12,
                  background: "var(--bg)",
                  border: "1px solid var(--panel-border)",
                  borderRadius: 8,
                  padding: 12,
                }}
              >
                {JSON.stringify(alertConfig.alert_message_template, null, 2)}
              </pre>

              <p style={{ color: "var(--dim)", fontSize: 11.5, marginTop: 10 }}>
                {alertConfig.note}
              </p>
            </>
          )}
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
              {unmappedSignals.length > 0 ? (
                <div>
                  <label style={{ fontSize: 11.5, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                    New alerts TradingView is already sending (not yet in the catalog)
                  </label>
                  <select
                    defaultValue=""
                    onChange={(e) => {
                      const picked = unmappedSignals.find(
                        (u) => `${u.strategy_key}@${u.strategy_version}` === e.target.value,
                      );
                      if (!picked) return;
                      setForm({
                        ...form,
                        strategy_key: picked.strategy_key,
                        strategy_version: picked.strategy_version,
                        name: humanizeStrategyKey(picked.strategy_key),
                        symbol: picked.symbol,
                        timeframe: picked.timeframe,
                      });
                    }}
                  >
                    <option value="" disabled>
                      Select an incoming alert...
                    </option>
                    {unmappedSignals.map((u) => (
                      <option key={`${u.strategy_key}@${u.strategy_version}`} value={`${u.strategy_key}@${u.strategy_version}`}>
                        {humanizeStrategyKey(u.strategy_key)} ({u.signal_count} signal
                        {u.signal_count === 1 ? "" : "s"})
                      </option>
                    ))}
                  </select>
                  <p style={{ fontSize: 11, color: "var(--dim)", marginTop: 4 }}>
                    Picking one fills in the fields below - you can still edit them before saving.
                  </p>
                </div>
              ) : null}
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
