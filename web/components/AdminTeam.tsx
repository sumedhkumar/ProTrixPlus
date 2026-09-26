"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AdminUser } from "@/lib/api";

const ADMIN_ROLES = [
  "SUPER_ADMIN",
  "OPERATIONS_ADMIN",
  "STRATEGY_ADMIN",
  "FINANCE_ADMIN",
  "AUDITOR",
] as const;

const ROLE_LABEL: Record<string, string> = {
  SUPER_ADMIN: "Super Admin",
  OPERATIONS_ADMIN: "Operations Admin",
  STRATEGY_ADMIN: "Strategy Admin",
  FINANCE_ADMIN: "Finance Admin",
  AUDITOR: "Auditor",
};

type Status = "Active" | "Invited" | "Deactivated";

function statusOf(a: AdminUser): Status {
  if (!a.is_active) return "Deactivated";
  if (!a.has_password) return "Invited";
  return "Active";
}

const STATUS_BADGE: Record<Status, string> = {
  Active: "badge-green",
  Invited: "badge-warn",
  Deactivated: "badge-bad",
};

interface ExistingAccountInfo {
  display_name: string;
  role: string;
  extra_roles: string[];
  subscription_package: string | null;
  is_active: boolean;
}

export function AdminTeam({ admins }: { admins: AdminUser[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", display_name: "", roles: [] as string[] });
  const [confirmContext, setConfirmContext] = useState<ExistingAccountInfo | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingRoles, setEditingRoles] = useState<string[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  function toggleFormRole(role: string) {
    setForm((f) => ({
      ...f,
      roles: f.roles.includes(role) ? f.roles.filter((r) => r !== role) : [...f.roles, role],
    }));
  }

  async function submitInvite(confirm: boolean) {
    setBusy("invite");
    setError(null);
    setNotice(null);
    const res = await fetch("/api/admin/invites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, confirm }),
    });
    setBusy(null);

    if (res.status === 409) {
      const body = (await res.json().catch(() => ({}))) as {
        detail?: { requires_confirmation?: boolean; existing?: ExistingAccountInfo; message?: string };
      };
      if (body.detail?.requires_confirmation && body.detail.existing) {
        setConfirmContext(body.detail.existing);
        return;
      }
      setError(body.detail?.message ?? "invite failed (409)");
      return;
    }
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(typeof body.detail === "string" ? body.detail : `invite failed (${res.status})`);
      return;
    }

    const data = (await res.json()) as { invited: boolean };
    setConfirmContext(null);
    setForm({ email: "", display_name: "", roles: [] });
    setNotice(
      data.invited
        ? "Invite sent."
        : "An account for this email already existed - its roles were updated instead of sending a new invite.",
    );
    router.refresh();
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    await submitInvite(false);
  }

  function startEdit(admin: AdminUser) {
    setError(null);
    setNotice(null);
    setEditingId(admin.id);
    setEditingRoles([admin.role, ...admin.extra_roles]);
  }

  function toggleEditRole(role: string) {
    setEditingRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role],
    );
  }

  async function saveRoles(id: string) {
    setBusy(id);
    setError(null);
    setNotice(null);
    const res = await fetch(`/api/admin/users/${id}/roles`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ roles: editingRoles }),
    });
    setBusy(null);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `update failed (${res.status})`);
      return;
    }
    setEditingId(null);
    router.refresh();
  }

  async function toggleActive(admin: AdminUser) {
    setBusy(admin.id);
    setError(null);
    setNotice(null);
    const action = admin.is_active ? "deactivate" : "reactivate";
    const res = await fetch(`/api/admin/users/${admin.id}/${action}`, { method: "POST" });
    setBusy(null);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `${action} failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  async function deleteUser(id: string) {
    setBusy(id);
    setError(null);
    setNotice(null);
    const res = await fetch(`/api/admin/users/${id}`, { method: "DELETE" });
    setBusy(null);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `delete failed (${res.status})`);
      setDeletingId(null);
      return;
    }
    setDeletingId(null);
    setNotice("Account permanently deleted.");
    router.refresh();
  }

  async function resendInvite(id: string) {
    setBusy(id);
    setError(null);
    setNotice(null);
    const res = await fetch(`/api/admin/users/${id}/resend-invite`, { method: "POST" });
    setBusy(null);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `resend failed (${res.status})`);
      return;
    }
    setNotice("Invite re-sent.");
    router.refresh();
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Admin team</span>
      </div>
      <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: -6, marginBottom: 14 }}>
        Invite a new admin by email and assign one or more roles - they get an
        email to set their password. An existing account&apos;s roles can also
        be edited here without re-inviting them.
      </p>

      <div style={{ overflowX: "auto" }}>
        <table data-testid="admin-team-list">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Roles</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {admins.map((a) => {
              const status = statusOf(a);
              return (
                <tr key={a.id}>
                  <td style={{ fontWeight: 700 }}>{a.display_name}</td>
                  <td>{a.email}</td>
                  <td>
                    {editingId === a.id ? (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {ADMIN_ROLES.map((role) => (
                          <label
                            key={role}
                            style={{ fontSize: 12, display: "flex", gap: 4, alignItems: "center" }}
                          >
                            <input
                              type="checkbox"
                              checked={editingRoles.includes(role)}
                              onChange={() => toggleEditRole(role)}
                            />
                            {ROLE_LABEL[role]}
                          </label>
                        ))}
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {[a.role, ...a.extra_roles].map((role) => (
                          <span key={role} className="badge-pill badge-blue">
                            {ROLE_LABEL[role] ?? role}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className={`badge-pill ${STATUS_BADGE[status]}`}>{status}</span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {editingId === a.id ? (
                        <>
                          <button
                            className="secondary"
                            disabled={busy === a.id || editingRoles.length === 0}
                            onClick={() => void saveRoles(a.id)}
                          >
                            Save
                          </button>
                          <button className="secondary" onClick={() => setEditingId(null)}>
                            Cancel
                          </button>
                        </>
                      ) : (
                        <button className="secondary" onClick={() => startEdit(a)}>
                          Edit roles
                        </button>
                      )}
                      {status === "Invited" ? (
                        <button
                          className="secondary"
                          disabled={busy === a.id}
                          onClick={() => void resendInvite(a.id)}
                        >
                          Resend invite
                        </button>
                      ) : null}
                      <button
                        className={a.is_active ? "btn-danger" : "secondary"}
                        disabled={busy === a.id}
                        onClick={() => void toggleActive(a)}
                      >
                        {a.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                      {status === "Deactivated" ? (
                        deletingId === a.id ? (
                          <>
                            <span style={{ fontSize: 12, color: "var(--bad)", alignSelf: "center" }}>
                              Permanently delete?
                            </span>
                            <button
                              className="btn-danger"
                              disabled={busy === a.id}
                              onClick={() => void deleteUser(a.id)}
                            >
                              {busy === a.id ? "Deleting..." : "Confirm delete"}
                            </button>
                            <button className="secondary" onClick={() => setDeletingId(null)}>
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button className="btn-danger" onClick={() => setDeletingId(a.id)}>
                            Delete permanently
                          </button>
                        )
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {admins.length === 0 ? <p className="empty">No admin accounts yet.</p> : null}
      </div>

      {confirmContext ? (
        <div className="pending-panel" style={{ textAlign: "left", marginTop: 16 }}>
          <strong>This email already has a client account</strong>
          <p style={{ color: "var(--muted)", fontSize: 12.5 }}>
            <strong>{confirmContext.display_name}</strong> currently holds{" "}
            {[confirmContext.role, ...confirmContext.extra_roles]
              .map((r) => ROLE_LABEL[r] ?? r)
              .join(", ")}
            {confirmContext.subscription_package
              ? ` and has a ${confirmContext.subscription_package} subscription`
              : ""}
            {confirmContext.is_active ? "" : " (currently deactivated)"}. Granting admin roles to
            this email will apply on top of their existing account.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="secondary" onClick={() => setConfirmContext(null)} disabled={busy === "invite"}>
              Cancel
            </button>
            <button
              className="btn-danger"
              disabled={busy === "invite"}
              onClick={() => void submitInvite(true)}
            >
              {busy === "invite" ? "Confirming..." : "Yes, grant admin roles anyway"}
            </button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => void invite(e)}
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 16 }}
        >
          <input
            placeholder="email"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
          <input
            placeholder="display name"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            required
          />
          <div style={{ gridColumn: "1 / -1", display: "flex", flexWrap: "wrap", gap: 10 }}>
            {ADMIN_ROLES.map((role) => (
              <label key={role} style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={form.roles.includes(role)}
                  onChange={() => toggleFormRole(role)}
                />
                {ROLE_LABEL[role]}
              </label>
            ))}
          </div>
          <button
            type="submit"
            disabled={busy === "invite" || form.roles.length === 0}
            style={{ gridColumn: "1 / -1" }}
          >
            Invite admin
          </button>
        </form>
      )}
      {notice ? (
        <p style={{ color: "var(--ok)", marginTop: 12 }} role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p style={{ color: "var(--bad)", marginTop: 12 }} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
