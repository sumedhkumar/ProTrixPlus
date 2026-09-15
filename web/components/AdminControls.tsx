"use client";

import { useState } from "react";

import type { AdminAssignment, AdminOperation } from "@/lib/api";

type Props = { operations: AdminOperation[]; assignments: AdminAssignment[] };

async function mutate(method: string, path: string, body: unknown) {
  const response = await fetch("/api/admin-control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ method, path, body }),
  });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.error ?? "Update failed");
}

export function AdminControls({ operations, assignments }: Props) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [credit, setCredit] = useState<Record<string, string>>({});

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key); setMessage(null);
    try { await fn(); setMessage("Saved. Refreshing operations data…"); window.location.reload(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Update failed"); setBusy(null); }
  }

  return <div className="panel">
    <h2>Admin controls</h2>
    <p style={{ color: "var(--muted)" }}>Changes are audit logged and enforced by the worker before every new entry.</p>
    {message ? <p role="status" style={{ color: "var(--warn)" }}>{message}</p> : null}
    <div className="control-grid">
      {operations.filter((op) => op.email !== "root@example.test").map((op) => {
        const controls = op.controls ?? { admin_suspended: false, risk_blocked: false, kill_switch: false };
        const amount = credit[op.user_id] ?? "";
        return <section className="control-card" key={op.user_id}>
          <h3>{op.display_name}</h3><code>{op.email}</code>
          <p>Wallet: <strong>USD {op.wallet_balance}</strong></p>
          <div className="control-row">
            <input aria-label={`${op.display_name} wallet credit`} inputMode="decimal" placeholder="Credit USD" value={amount} onChange={(e) => setCredit({ ...credit, [op.user_id]: e.target.value })} />
            <button disabled={busy !== null || !Number(amount)} onClick={() => void run(`credit-${op.user_id}`, () => mutate("POST", "/api/v1/admin/wallet/top-ups", { user_id: op.user_id, amount, idempotency_key: `admin-ui:${crypto.randomUUID()}`, reason: "Manual MVP rent credit" }))}>Credit</button>
          </div>
          <div className="control-actions">
            <button className={controls.kill_switch ? "danger" : "secondary"} disabled={busy !== null} onClick={() => void run(`kill-${op.user_id}`, () => mutate("PUT", `/api/v1/admin/users/${op.user_id}/controls`, { ...controls, kill_switch: !controls.kill_switch }))}>{controls.kill_switch ? "Release kill switch" : "Kill switch"}</button>
            <button className="secondary" disabled={busy !== null} onClick={() => void run(`suspend-${op.user_id}`, () => mutate("PUT", `/api/v1/admin/users/${op.user_id}/controls`, { ...controls, admin_suspended: !controls.admin_suspended }))}>{controls.admin_suspended ? "Unsuspend" : "Suspend"}</button>
            <button className="secondary" disabled={busy !== null} onClick={() => void run(`risk-${op.user_id}`, () => mutate("PUT", `/api/v1/admin/users/${op.user_id}/controls`, { ...controls, risk_blocked: !controls.risk_blocked }))}>{controls.risk_blocked ? "Unblock risk" : "Block risk"}</button>
          </div>
          <details><summary>Subscription and risk settings</summary>
            <SettingsForm op={op} busy={busy !== null} onRun={run} />
          </details>
          <details><summary>Account metadata</summary>
            <AccountForm op={op} busy={busy !== null} onRun={run} />
          </details>
        </section>;
      })}
    </div>
    <div className="control-grid" style={{ marginTop: 16 }}>
      {assignments.map((assignment) => <AssignmentForm key={assignment.id} assignment={assignment} busy={busy !== null} onRun={run} />)}
    </div>
  </div>;
}

function SettingsForm({ op, busy, onRun }: { op: AdminOperation; busy: boolean; onRun: (key: string, fn: () => Promise<void>) => Promise<void> }) {
  const subscription = op.subscription;
  const risk = op.risk;
  const [plan, setPlan] = useState(subscription?.plan_code ?? "MVP_DEMO");
  const [subStatus, setSubStatus] = useState<string>(subscription?.status ?? "ACTIVE");
  const [maxLot, setMaxLot] = useState(risk?.max_lot ?? "1.00");
  const [maxOpen, setMaxOpen] = useState(String(risk?.max_open_trades ?? 1));
  const [maxLoss, setMaxLoss] = useState(risk?.max_daily_loss ?? "0.00");
  const [symbols, setSymbols] = useState((risk?.allowed_symbols ?? ["XAUUSD"]).join(","));
  const start = subscription?.starts_at ?? new Date().toISOString();
  const end = subscription?.ends_at ?? new Date(Date.now() + 365 * 86400000).toISOString();
  return <div className="control-form">
    <label>Plan <input value={plan} onChange={(e) => setPlan(e.target.value)} /></label>
    <label>Status <select value={subStatus} onChange={(e) => setSubStatus(e.target.value)}><option>ACTIVE</option><option>EXPIRED</option><option>DISABLED</option></select></label>
    <button disabled={busy} onClick={() => void onRun(`sub-${op.user_id}`, () => mutate("PUT", `/api/v1/admin/users/${op.user_id}/subscription`, { plan_code: plan, status: subStatus, starts_at: start, ends_at: end }))}>Save subscription</button>
    <label>Max lot <input inputMode="decimal" value={maxLot} onChange={(e) => setMaxLot(e.target.value)} /></label>
    <label>Max open <input inputMode="numeric" value={maxOpen} onChange={(e) => setMaxOpen(e.target.value)} /></label>
    <label>Daily loss <input inputMode="decimal" value={maxLoss} onChange={(e) => setMaxLoss(e.target.value)} /></label>
    <label>Symbols <input value={symbols} onChange={(e) => setSymbols(e.target.value)} /></label>
    <button disabled={busy} onClick={() => void onRun(`limits-${op.user_id}`, () => mutate("PUT", `/api/v1/admin/users/${op.user_id}/risk-profile`, { max_lot: maxLot, max_open_trades: Number(maxOpen), max_daily_loss: maxLoss, allowed_symbols: symbols.split(",").map((s) => s.trim()).filter(Boolean) }))}>Save risk limits</button>
  </div>;
}

function AssignmentForm({ assignment, busy, onRun }: { assignment: AdminAssignment; busy: boolean; onRun: (key: string, fn: () => Promise<void>) => Promise<void> }) {
  const [multiplier, setMultiplier] = useState(assignment.multiplier);
  const [status, setStatus] = useState<string>(assignment.status);
  return <section className="control-card"><h3>{assignment.user_display_name} · {assignment.strategy_key}</h3><div className="control-row"><input aria-label={`${assignment.user_display_name} multiplier`} inputMode="decimal" value={multiplier} onChange={(e) => setMultiplier(e.target.value)} /><select value={status} onChange={(e) => setStatus(e.target.value)}><option>ACTIVE</option><option>PAUSED</option></select><button disabled={busy} onClick={() => void onRun(`assignment-${assignment.id}`, () => mutate("PATCH", `/api/v1/admin/assignments/${assignment.id}`, { multiplier, status }))}>Save assignment</button></div></section>;
}

function AccountForm({ op, busy, onRun }: { op: AdminOperation; busy: boolean; onRun: (key: string, fn: () => Promise<void>) => Promise<void> }) {
  const account = op.account;
  const [provider, setProvider] = useState(account?.provider_name ?? "Local development");
  const [server, setServer] = useState(account?.server_identifier ?? "");
  const [category, setCategory] = useState(account?.category ?? "DEMO");
  const [transport, setTransport] = useState(account?.transport ?? "MOCK");
  const [status, setStatus] = useState(account?.status ?? "ACTIVE");
  return <div className="control-form"><label>Provider <input value={provider} onChange={(e) => setProvider(e.target.value)} /></label><label>Server <input value={server} onChange={(e) => setServer(e.target.value)} /></label><label>Category <select value={category} onChange={(e) => setCategory(e.target.value)}><option>DEMO</option><option>LIVE</option></select></label><label>Transport <select value={transport} onChange={(e) => setTransport(e.target.value)}><option>MOCK</option><option>NATIVE_MT5</option><option>METAAPI</option></select></label><label>Status <select value={status} onChange={(e) => setStatus(e.target.value)}><option>ACTIVE</option><option>DISABLED</option></select></label><button disabled={busy} onClick={() => void onRun(`account-${op.user_id}`, () => mutate("PUT", `/api/v1/admin/users/${op.user_id}/account`, { provider_name: provider, server_identifier: server || null, category, transport, status, external_account_ref: account?.external_account_ref, credential_key_ref: account?.credential_key_ref }))}>Save account metadata</button></div>;
}
