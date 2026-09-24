"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AdminAssignment, AdminMt5ConnectionView, AdminUser } from "@/lib/api";

import { MetaApiAttachCell } from "./MetaApiAttachCell";

export function AdminClientsOverview({
  users,
  assignments,
  mt5Connections,
  canDeactivate,
}: {
  users: AdminUser[];
  assignments: AdminAssignment[];
  mt5Connections: AdminMt5ConnectionView[];
  /** Only SUPER_ADMIN can deactivate/reactivate a client account. */
  canDeactivate: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const clients = users.filter((u) => u.role === "USER");
  const mt5ByUser = new Map(mt5Connections.map((c) => [c.user_display_name, c]));

  async function toggleActive(user: AdminUser) {
    setBusy(user.id);
    setError(null);
    const action = user.is_active ? "deactivate" : "reactivate";
    const res = await fetch(`/api/admin/users/${user.id}/${action}`, { method: "POST" });
    setBusy(null);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `${action} failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Client accounts, MT5 bridges &amp; entitlements</span>
        <span className="badge-pill badge-neutral">{clients.length} registered</span>
      </div>
      {clients.length === 0 ? (
        <div className="empty">No clients signed up yet.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table data-testid="admin-clients-overview">
            <thead>
              <tr>
                <th>Client</th>
                <th>MT5 bridge</th>
                <th>Bridge state</th>
                <th>MetaApi (real order routing)</th>
                <th>Active subscriptions</th>
                <th>Account state</th>
                <th>Account</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((u) => {
                const mt5 = mt5ByUser.get(u.display_name);
                const clientAssignments = assignments.filter(
                  (a) => a.user_display_name === u.display_name,
                );
                return (
                  <tr key={u.id}>
                    <td>
                      <div style={{ fontWeight: 700 }}>{u.display_name}</div>
                      <div style={{ color: "var(--muted)", fontSize: 12 }}>{u.email}</div>
                    </td>
                    <td>{mt5 ? `${mt5.broker_server} / ${mt5.login}` : "-"}</td>
                    <td>
                      {mt5 ? (
                        <span
                          className={`badge-pill ${mt5.status === "CONNECTED" ? "badge-green" : "badge-warn"}`}
                        >
                          {mt5.status}
                        </span>
                      ) : (
                        <span className="badge-pill badge-neutral">NOT CONFIGURED</span>
                      )}
                    </td>
                    <td>
                      <MetaApiAttachCell connection={mt5} />
                    </td>
                    <td>
                      {clientAssignments.length === 0
                        ? "None"
                        : clientAssignments
                            .map((a) => `${a.strategy_key} (${a.multiplier}x)`)
                            .join(", ")}
                    </td>
                    <td>
                      <span className={`badge-pill ${u.is_active ? "badge-green" : "badge-bad"}`}>
                        {u.is_active ? "ENABLED" : "DISABLED"}
                      </span>
                    </td>
                    <td>
                      {canDeactivate ? (
                        <button
                          className={u.is_active ? "btn-danger" : "secondary"}
                          disabled={busy === u.id}
                          onClick={() => void toggleActive(u)}
                        >
                          {u.is_active ? "Deactivate" : "Reactivate"}
                        </button>
                      ) : (
                        <span style={{ color: "var(--dim)", fontSize: 12 }}>-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {error ? (
        <p style={{ color: "var(--bad)", marginTop: 12 }} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
