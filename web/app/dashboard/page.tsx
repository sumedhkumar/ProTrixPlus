import { redirect } from "next/navigation";

import { ExecutionsTable } from "@/components/ExecutionsTable";
import { IdentityBar } from "@/components/IdentityBar";
import { SignalsTable } from "@/components/SignalsTable";
import {
  apiFetch,
  type ExecutionView,
  type Identity,
  type Portfolio,
  type SignalView,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const token = getToken();
  if (!token) redirect("/login");

  let identity: Identity;
  try {
    identity = await apiFetch<Identity>("/api/v1/me", token);
  } catch {
    redirect("/login");
  }

  const [signals, executions, portfolio] = await Promise.all([
    apiFetch<SignalView[]>("/api/v1/signals", token),
    apiFetch<ExecutionView[]>("/api/v1/executions", token),
    apiFetch<Portfolio>("/api/v1/portfolio", token),
  ]);
  const latestSignal = signals[0];

  return (
    <>
      <IdentityBar identity={identity} />
      <div className="container">
        <h1>User dashboard</h1>
        <p style={{ color: "var(--muted)" }}>
          Your server-enforced account, controls, signals, and executions.
        </p>
        <div className="panel">
          <h2>Trading access</h2>
          <div className="summary-grid">
            <div><span>Wallet</span><strong>{portfolio.wallet.currency} {portfolio.wallet.balance}</strong></div>
            <div><span>Subscription</span><strong>{portfolio.subscription?.status ?? "NOT CONFIGURED"}</strong></div>
            <div><span>Account</span><strong>{portfolio.account ? `${portfolio.account.category} / ${portfolio.account.transport} / ${portfolio.account.status}` : "NOT CONFIGURED"}</strong></div>
            <div><span>Execution worker</span><strong>{portfolio.account?.worker_status ?? "NO WORKER"}</strong></div>
            <div><span>Safety</span><strong>{portfolio.controls?.kill_switch ? "KILL SWITCH ON" : portfolio.controls?.admin_suspended ? "SUSPENDED" : portfolio.controls?.risk_blocked ? "RISK BLOCKED" : "CLEAR"}</strong></div>
          </div>
        </div>
        <div className="panel">
          <h2>Execution route</h2>
          <p style={{ color: "var(--muted)" }}>
            {portfolio.account?.worker_status === "HEALTHY"
              ? `Native worker ${portfolio.account.worker_name ?? ""} last checked in ${portfolio.account.worker_heartbeat_at ?? "just now"}.`
              : "No recent native worker heartbeat. New entries remain subject to worker availability and server-side controls."}
          </p>
        </div>
        <div className="panel">
          <h2>Alert delivery</h2>
          <p style={{ color: "var(--muted)" }}>
            {latestSignal
              ? `Latest accepted alert: ${latestSignal.action} ${latestSignal.symbol} at ${latestSignal.accepted_at}; ${latestSignal.intent_count} intent(s) created for your route.`
              : "Waiting for the first eligible TradingView alert for this route."}
          </p>
        </div>
        <div className="panel">
          <h2>Strategy settings</h2>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead><tr><th>strategy</th><th>master lot</th><th>multiplier</th><th>allowed range</th><th>status</th></tr></thead>
              <tbody>
                {portfolio.assignments.map((assignment) => (
                  <tr key={assignment.id}>
                    <td>{assignment.strategy_key}@{assignment.strategy_version}</td>
                    <td>{assignment.master_lot}</td>
                    <td>{assignment.multiplier}</td>
                    <td>{assignment.multiplier_min}–{assignment.multiplier_max}</td>
                    <td>{assignment.status}</td>
                  </tr>
                ))}
                {!portfolio.assignments.length ? <tr><td className="empty" colSpan={5}>No assignment configured.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <h2>Managed positions</h2>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead><tr><th>symbol</th><th>side</th><th>remaining</th><th>state</th><th>source reference</th></tr></thead>
              <tbody>
                {portfolio.managed_positions.map((position) => (
                  <tr key={position.id}><td>{position.symbol}</td><td>{position.side}</td><td>{position.remaining_volume}</td><td>{position.status}</td><td><code>{position.source_position_ref}</code></td></tr>
                ))}
                {!portfolio.managed_positions.length ? <tr><td className="empty" colSpan={5}>No managed positions yet.</td></tr> : null}
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
