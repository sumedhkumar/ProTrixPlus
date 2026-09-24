"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AlertChangelogEntry, AlertView } from "@/lib/api";

export function AdminAlertCatalog({
  alerts,
  canEdit,
}: {
  alerts: AlertView[];
  /** STRATEGY_ADMIN/SUPER_ADMIN can create alerts; everyone else views the catalog read-only. */
  canEdit: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [changelogFor, setChangelogFor] = useState<string | null>(null);
  const [changelog, setChangelog] = useState<AlertChangelogEntry[]>([]);
  const [form, setForm] = useState({ name: "", symbol: "", lot_size: "", timeframe: "" });

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/admin/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: form.name,
        symbol: form.symbol,
        lot_size: form.lot_size,
        timeframe: form.timeframe,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `create failed (${res.status})`);
      return;
    }
    setForm({ name: "", symbol: "", lot_size: "", timeframe: "" });
    router.refresh();
  }

  async function viewChangelog(id: string) {
    setChangelogFor(id);
    setChangelog([]);
    const res = await fetch(`/api/admin/alerts/${id}/changelog`);
    if (res.ok) setChangelog((await res.json()) as AlertChangelogEntry[]);
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">TradingView Alert Catalog</span>
      </div>
      <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: -6, marginBottom: 14 }}>
        Define an alert here (symbol, lot size, timeframe), then paste its config into
        TradingView&apos;s own alert dialog. Bundle one or more alerts into a strategy from the
        Strategy Lifecycle tab. Every field change is recorded below with a full changelog.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table data-testid="admin-alert-catalog">
          <thead>
            <tr>
              <th>Name</th>
              <th>Symbol</th>
              <th>Lot size</th>
              <th>Timeframe</th>
              <th>Strategy</th>
              <th>Last updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id}>
                <td style={{ fontWeight: 700 }}>{a.name}</td>
                <td>
                  <span className="badge-pill badge-blue">{a.symbol}</span>
                </td>
                <td>{a.lot_size}</td>
                <td>{a.timeframe}</td>
                <td>
                  <span className={`badge-pill ${a.strategy_id ? "badge-green" : "badge-neutral"}`}>
                    {a.strategy_id ? "Bundled" : "Unbundled"}
                  </span>
                </td>
                <td style={{ fontSize: 11.5, color: "var(--muted)" }}>
                  {new Date(a.updated_at).toLocaleString()}
                </td>
                <td>
                  <button className="secondary" onClick={() => void viewChangelog(a.id)}>
                    Changelog
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {changelogFor ? (
        <div className="pending-panel" style={{ textAlign: "left", marginTop: 14 }}>
          <strong>Changelog</strong>
          {changelog.length === 0 ? (
            <p style={{ color: "var(--muted)", fontSize: 12.5 }}>No changes recorded yet.</p>
          ) : (
            <ul style={{ fontSize: 12.5, paddingLeft: 18 }}>
              {changelog.map((entry, i) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  <span style={{ color: "var(--dim)" }}>
                    {new Date(entry.created_at).toLocaleString()} —{" "}
                  </span>
                  {entry.event_type === "alert.field_changed" ? (
                    <>
                      <code>{String(entry.data.field)}</code>: {String(entry.data.old_value)} →{" "}
                      {String(entry.data.new_value)}
                    </>
                  ) : (
                    entry.event_type
                  )}
                  {entry.actor ? (
                    <span style={{ color: "var(--dim)" }}> (by {entry.actor})</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <button className="secondary" onClick={() => setChangelogFor(null)}>
            Close
          </button>
        </div>
      ) : null}

      {canEdit ? (
        <form
          onSubmit={(e) => void create(e)}
          style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginTop: 16 }}
        >
          <input
            placeholder="name (e.g. EURUSD Scalper Entry)"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <input
            placeholder="symbol (e.g. EURUSD)"
            value={form.symbol}
            onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
            required
          />
          <input
            placeholder="lot size"
            value={form.lot_size}
            onChange={(e) => setForm({ ...form, lot_size: e.target.value })}
            required
          />
          <input
            placeholder="timeframe (e.g. 5m)"
            value={form.timeframe}
            onChange={(e) => setForm({ ...form, timeframe: e.target.value })}
            required
          />
          <button type="submit" disabled={busy}>
            Create alert
          </button>
        </form>
      ) : (
        <p style={{ color: "var(--dim)", fontSize: 12, marginTop: 16 }}>
          Read-only: your role can&apos;t create or edit alerts.
        </p>
      )}
      {error ? (
        <p style={{ color: "var(--bad)", marginTop: 12 }} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
