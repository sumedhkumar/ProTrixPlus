import { redirect } from "next/navigation";

import { ExecutionsTable } from "@/components/ExecutionsTable";
import { AdminControls } from "@/components/AdminControls";
import { MarketplaceAdminControls } from "@/components/MarketplaceAdminControls";
import { IdentityBar } from "@/components/IdentityBar";
import { Icon } from "@/components/Icon";
import { SignalsTable } from "@/components/SignalsTable";
import {
  apiFetch,
  type AdminAssignment,
  type AdminOperation,
  type AdminUser,
  type ExecutionView,
  type Identity,
  type AdminMarketplaceEnrollment,
  type MarketplaceOffer,
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

  const [users, assignments, operations, signals, executions, offers, marketplaceEnrollments] = await Promise.all([
    apiFetch<AdminUser[]>("/api/v1/admin/users", token),
    apiFetch<AdminAssignment[]>("/api/v1/admin/assignments", token),
    apiFetch<AdminOperation[]>("/api/v1/admin/operations", token),
    apiFetch<SignalView[]>("/api/v1/signals", token),
    apiFetch<ExecutionView[]>("/api/v1/executions", token),
    apiFetch<MarketplaceOffer[]>("/api/v1/admin/marketplace/offers", token),
    apiFetch<AdminMarketplaceEnrollment[]>("/api/v1/admin/marketplace/enrollments", token),
  ]);
  const managementReview = executions.filter(
    (execution) => execution.state === "UNKNOWN" && execution.command_target !== "ENTRY",
  );

  return (
    <>
      <IdentityBar identity={identity} />
      <main id="main-content" className="container app-content">
        <div className="page-heading"><div><h1>Super Admin dashboard</h1><p>Manage access, monitor execution, and keep every account in view.</p></div><span className="status-muted"><Icon name="shield" size={15} /> Administrator access</span></div>
        <section className="metrics-grid" aria-label="Operations overview">
          <div className="metric-card metric-card-accent"><div className="metric-label">Registered users <Icon name="user" /></div><strong className="metric-value">{users.length}</strong><span className="metric-caption">{users.filter((user) => user.is_active).length} active users</span></div>
          <div className="metric-card"><div className="metric-label">Strategy assignments <Icon name="layers" /></div><strong className="metric-value">{assignments.length}</strong><span className="metric-caption">{assignments.filter((assignment) => assignment.status === "ACTIVE").length} active assignments</span></div>
          <div className="metric-card"><div className="metric-label">Healthy workers <Icon name="activity" /></div><strong className="metric-value">{operations.filter((operation) => operation.account?.worker_status === "HEALTHY").length}</strong><span className="metric-caption">Across {operations.filter((operation) => operation.account).length} configured accounts</span></div>
          <div className="metric-card"><div className="metric-label">Management review <Icon name="shield" /></div><strong className="metric-value">{managementReview.length}</strong><span className={managementReview.length ? "status-warn" : "status-good"}>{managementReview.length ? "Needs attention" : "No pending reviews"}</span></div>
        </section>

        <div className="panel">
          <h2>Trading operations</h2>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead><tr><th>user</th><th>wallet</th><th>subscription</th><th>execution account</th><th>worker</th><th>safety</th><th>risk</th></tr></thead>
              <tbody>
                {operations.map((op) => (
                  <tr key={op.user_id}>
                    <td>{op.display_name}<br /><code>{op.email}</code></td>
                    <td>USD {op.wallet_balance}</td>
                    <td>{op.subscription_status ?? "NOT CONFIGURED"}</td>
                    <td>{op.account ? `${op.account.category} / ${op.account.transport} / ${op.account.status}` : "NOT CONFIGURED"}</td>
                    <td>{op.account ? `${op.account.worker_status}${op.account.worker_name ? ` (${op.account.worker_name})` : ""}` : "NO WORKER"}</td>
                    <td>{op.controls?.kill_switch ? "KILL SWITCH" : op.controls?.admin_suspended ? "SUSPENDED" : op.controls?.risk_blocked ? "RISK BLOCKED" : "CLEAR"}</td>
                    <td>{op.risk ? `${op.risk.max_lot} lot, ${op.risk.max_open_trades} open` : "NOT CONFIGURED"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <AdminControls operations={operations} assignments={assignments} />
        <MarketplaceAdminControls users={users} offers={offers} enrollments={marketplaceEnrollments} />

        <div className="panel">
          <h2>Management review queue</h2>
          <p style={{ color: "var(--muted)" }}>
            Unknown close, partial-close, or SL/TP changes are never resent automatically. Verify the broker position first, then resolve through the mapped position workflow.
          </p>
          {managementReview.length ? (
            <div style={{ overflowX: "auto" }}>
              <table><thead><tr><th>user</th><th>signal</th><th>command</th><th>reason</th><th>updated</th></tr></thead><tbody>{managementReview.map((execution) => <tr key={execution.id}><td>{execution.user_display_name}</td><td>{execution.signal_ref}</td><td>{execution.command_target}</td><td>{execution.last_error ?? "Broker response unknown"}</td><td>{execution.updated_at}</td></tr>)}</tbody></table>
            </div>
          ) : <div className="empty">No management actions require review.</div>}
        </div>

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
      </main>
    </>
  );
}
