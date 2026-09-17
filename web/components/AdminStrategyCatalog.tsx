"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { StrategyView } from "@/lib/api";

export function AdminStrategyCatalog({ strategies }: { strategies: StrategyView[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alertConfigFor, setAlertConfigFor] = useState<string | null>(null);
  const [alertConfigBody, setAlertConfigBody] = useState<string>("");
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
      }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `create failed (${res.status})`);
      return;
    }
    setForm({ ...form, strategy_key: "", name: "" });
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
      setError(`toggle failed (${res.status})`);
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

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Strategy Lifecycle &amp; Catalog Management</span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table data-testid="admin-strategy-catalog">
          <thead>
            <tr>
              <th>Strategy &amp; symbol</th>
              <th>Timeframe</th>
              <th>Base lot</th>
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
                    {s.is_active ? "ACTIVE" : "PAUSED"}
                  </span>
                </td>
                <td>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => void toggle(s.id, s.is_active)}
                    >
                      Turn {s.is_active ? "OFF" : "ON"}
                    </button>
                    <button className="secondary" onClick={() => void viewAlertConfig(s.id)}>
                      Alert config
                    </button>
                  </div>
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

      <form
        onSubmit={(e) => void create(e)}
        style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginTop: 16 }}
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
        <input
          placeholder="base lot"
          value={form.base_lot}
          onChange={(e) => setForm({ ...form, base_lot: e.target.value })}
        />
        <input
          placeholder="description"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
        <button type="submit" disabled={busy}>
          Create strategy
        </button>
      </form>
      {error ? (
        <p style={{ color: "var(--bad)", marginTop: 12 }} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
