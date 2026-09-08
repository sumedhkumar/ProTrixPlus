import { redirect } from "next/navigation";

import { ExecutionsTable } from "@/components/ExecutionsTable";
import { IdentityBar } from "@/components/IdentityBar";
import { SignalsTable } from "@/components/SignalsTable";
import {
  apiFetch,
  type AdminAssignment,
  type AdminUser,
  type ExecutionView,
  type Identity,
  type SignalView,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { canAccessAdmin } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const token = getToken();
  if (!token) redirect("/login");

  let identity: Identity;
  try {
    identity = await apiFetch<Identity>("/api/v1/me", token);
  } catch {
    redirect("/login");
  }

  // A USER token must not see this shell. The api also rejects the admin calls
  // below with 403 - this is the client-side half of the same gate.
  if (!canAccessAdmin(identity.role)) {
    redirect("/dashboard");
  }

  const [users, assignments, signals, executions] = await Promise.all([
    apiFetch<AdminUser[]>("/api/v1/admin/users", token),
    apiFetch<AdminAssignment[]>("/api/v1/admin/assignments", token),
    apiFetch<SignalView[]>("/api/v1/signals", token),
    apiFetch<ExecutionView[]>("/api/v1/executions", token),
  ]);

  return (
    <>
      <IdentityBar identity={identity} />
      <div className="container">
        <h1>Super Admin dashboard</h1>
        <p style={{ color: "var(--muted)" }}>All users, assignments, signals and executions.</p>

        <div className="panel">
          <h2>Users</h2>
          <div style={{ overflowX: "auto" }}>
            <table data-testid="admin-users">
              <thead>
                <tr>
                  <th>name</th>
                  <th>email</th>
                  <th>role</th>
                  <th>active</th>
                  <th>assignments</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.display_name}</td>
                    <td>{u.email}</td>
                    <td>
                      <code>{u.role}</code>
                    </td>
                    <td>{u.is_active ? "yes" : "no"}</td>
                    <td>{u.assignment_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <h2>Strategy assignments</h2>
          <div style={{ overflowX: "auto" }}>
            <table data-testid="admin-assignments">
              <thead>
                <tr>
                  <th>user</th>
                  <th>strategy</th>
                  <th>master_lot</th>
                  <th>multiplier</th>
                  <th>bounds</th>
                  <th>status</th>
                </tr>
              </thead>
              <tbody>
                {assignments.map((a) => (
                  <tr key={a.id}>
                    <td>{a.user_display_name}</td>
                    <td>
                      {a.strategy_key}@{a.strategy_version}
                    </td>
                    <td>{a.master_lot}</td>
                    <td>{a.multiplier}</td>
                    <td>
                      {a.multiplier_min}–{a.multiplier_max}
                    </td>
                    <td>{a.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <SignalsTable signals={signals} />
        <ExecutionsTable executions={executions} />
      </div>
    </>
  );
}
