"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AdminAssignment, AdminUser, StrategyView } from "@/lib/api";

export function AdminGrantEntitlement({
  users,
  strategies,
  assignments,
  canManage,
}: {
  users: AdminUser[];
  strategies: StrategyView[];
  assignments: AdminAssignment[];
  /** FINANCE_ADMIN/SUPER_ADMIN can grant/revoke; everyone else sees the ledger read-only. */
  canManage: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    user_id: "",
    strategy_id: "",
    master_lot: "1.00",
    multiplier: "1",
    multiplier_min: "1",
    multiplier_max: "3",
  });

  async function grant(e: React.FormEvent) {
    e.preventDefault();
    setBusy("grant");
    setError(null);
    const res = await fetch("/api/admin/assignments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: form.user_id,
        strategy_id: form.strategy_id,
        master_lot: form.master_lot,
        multiplier: Number(form.multiplier),
        multiplier_min: Number(form.multiplier_min),
        multiplier_max: Number(form.multiplier_max),
      }),
    });
    setBusy(null);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `grant failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  async function revoke(assignmentId: string) {
    setBusy(assignmentId);
    setError(null);
    const res = await fetch(`/api/admin/assignments/${assignmentId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ revoke: true }),
    });
    setBusy(null);
    if (!res.ok) {
      setError(`revoke failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Grant / revoke entitlement</span>
      </div>

      {canManage ? (
        <form
          onSubmit={(e) => void grant(e)}
          style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}
        >
          <select
            value={form.user_id}
            onChange={(e) => setForm({ ...form, user_id: e.target.value })}
            required
          >
            <option value="">Select client...</option>
            {users
              .filter((u) => u.role === "USER")
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name} ({u.email})
                </option>
              ))}
          </select>
          <select
            value={form.strategy_id}
            onChange={(e) => setForm({ ...form, strategy_id: e.target.value })}
            required
          >
            <option value="">Select strategy...</option>
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.strategy_key}@{s.strategy_version})
              </option>
            ))}
          </select>
          <input
            placeholder="master lot"
            value={form.master_lot}
            onChange={(e) => setForm({ ...form, master_lot: e.target.value })}
            required
          />
          <input
            placeholder="initial multiplier"
            value={form.multiplier}
            onChange={(e) => setForm({ ...form, multiplier: e.target.value })}
          />
          <input
            placeholder="multiplier min"
            value={form.multiplier_min}
            onChange={(e) => setForm({ ...form, multiplier_min: e.target.value })}
          />
          <input
            placeholder="multiplier max"
            value={form.multiplier_max}
            onChange={(e) => setForm({ ...form, multiplier_max: e.target.value })}
          />
          <button type="submit" disabled={busy !== null}>
            Grant access
          </button>
        </form>
      ) : (
        <p style={{ color: "var(--dim)", fontSize: 12 }}>
          Read-only: your role can&apos;t grant or revoke entitlements.
        </p>
      )}

      <div style={{ overflowX: "auto", marginTop: 16 }}>
        <table data-testid="admin-grant-list">
          <thead>
            <tr>
              <th>user</th>
              <th>strategy</th>
              <th>entitlement</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {assignments.map((a) => (
              <tr key={a.id}>
                <td>{a.user_display_name}</td>
                <td>
                  {a.strategy_key}@{a.strategy_version}
                </td>
                <td>{a.status}</td>
                <td>
                  {canManage ? (
                    <button
                      className="secondary"
                      disabled={busy === a.id}
                      onClick={() => void revoke(a.id)}
                    >
                      Revoke
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error ? (
        <p style={{ color: "var(--bad)", marginTop: 12 }} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
