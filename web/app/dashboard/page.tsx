import Link from "next/link";
import { redirect } from "next/navigation";

import { ExecutionsTable } from "@/components/ExecutionsTable";
import { Icon } from "@/components/Icon";
import { IdentityBar } from "@/components/IdentityBar";
import { SignalsTable } from "@/components/SignalsTable";
import { StrategyEnrollmentPanel } from "@/components/StrategyEnrollmentPanel";
import {
  apiFetch,
  type ExecutionView,
  type Identity,
  type Portfolio,
  type SignalView,
  type StrategyEnrollmentView,
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

  const [signals, executions, portfolio, enrollments] = await Promise.all([
    apiFetch<SignalView[]>("/api/v1/signals", token),
    apiFetch<ExecutionView[]>("/api/v1/executions", token),
    apiFetch<Portfolio>("/api/v1/portfolio", token),
    apiFetch<StrategyEnrollmentView[]>("/api/v1/marketplace/enrollments", token),
  ]);
  const latestSignal = signals[0];
  const healthy = portfolio.account?.worker_status === "HEALTHY";
  const safety = portfolio.controls?.kill_switch ? "Kill switch on" : portfolio.controls?.admin_suspended ? "Suspended" : portfolio.controls?.risk_blocked ? "Risk blocked" : portfolio.controls ? "Clear" : "Not configured";
  const activeStrategies = enrollments.filter((enrollment) => enrollment.status === "ACTIVE").length;

  return (
    <>
      <IdentityBar identity={identity} />
      <main id="main-content" className="container app-content">
        <div className="page-heading">
          <div><h1>User dashboard</h1><p>Welcome back, {identity.display_name.split(" ")[0]}. Here&apos;s your trading overview.</p></div>
          <Link href="/marketplace" className="button-link"><Icon name="layers" size={17} /> Explore strategies <Icon name="arrow" size={17} /></Link>
        </div>

        <section className="metrics-grid" aria-label="Trading access">
          <div className="metric-card metric-card-accent"><div className="metric-label">Wallet balance <Icon name="wallet" /></div><strong className="metric-value"><small>{portfolio.wallet.currency}</small>{Number(portfolio.wallet.balance).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong><span className="metric-caption">Subscription: {portfolio.subscription?.status.replaceAll("_", " ") ?? "Not configured"}</span></div>
          <div className="metric-card"><div className="metric-label">Active strategies <Icon name="layers" /></div><strong className="metric-value">{activeStrategies.toString().padStart(2, "0")}</strong><span className="metric-caption">{enrollments.length} total strategy enrollment{enrollments.length === 1 ? "" : "s"}</span></div>
          <div className="metric-card"><div className="metric-label">Trading account <Icon name="server" /></div><strong className="metric-value metric-value-text">{portfolio.account?.category ?? "Not connected"}</strong><span className="metric-caption">{portfolio.account ? `${portfolio.account.transport.replaceAll("_", " ")} · ${portfolio.account.status}` : "Set up an account to begin"}</span></div>
          <div className="metric-card"><div className="metric-label">Safety controls <Icon name="shield" /></div><strong className="metric-value metric-value-text">{safety}</strong><span className={safety === "Clear" ? "status-good" : "status-warn"}><span className="status-dot" />{safety === "Clear" ? "No safety blocks" : "Review required"}</span></div>
        </section>

        <section className="connection-grid" aria-label="Signal and execution connections">
          <div className="connection-card"><span className="connection-icon"><Icon name="activity" /></span><div><h2>Execution route</h2><p>{healthy ? `Worker ${portfolio.account?.worker_name ?? "connected"}` : "Waiting for a worker heartbeat"}</p><small>{healthy ? `Last check-in: ${portfolio.account?.worker_heartbeat_at ?? "just now"}` : "New entries depend on worker availability and account controls."}</small></div><span className={healthy ? "status-good" : "status-warn"}><span className="status-dot" />{healthy ? "Healthy" : "Not connected"}</span></div>
          <div className="connection-card"><span className="connection-icon"><Icon name="signal" /></span><div><h2>Alert delivery</h2><p>{latestSignal ? `${latestSignal.action} ${latestSignal.symbol} · ${latestSignal.intent_count} intent(s)` : "Listening for your first alert"}</p><small>{latestSignal ? `Latest accepted: ${latestSignal.accepted_at}` : "Eligible TradingView alerts will appear here."}</small></div></div>
        </section>

        <StrategyEnrollmentPanel enrollments={enrollments} />

        <section className="panel">
          <div className="panel-header"><div><h2>Strategy settings <span className="badge">{portfolio.assignments.length}</span></h2><p>Position sizing and assignment status.</p></div><Icon name="layers" /></div>
          <div className="table-scroll" role="region" aria-label="Strategy settings" tabIndex={0}>
            <table>
              <thead><tr><th scope="col">Strategy</th><th scope="col">Master lot</th><th scope="col">Multiplier</th><th scope="col">Allowed range</th><th scope="col">Status</th></tr></thead>
              <tbody>
                {portfolio.assignments.map((assignment) => (
                  <tr key={assignment.id}><td>{assignment.strategy_key}@{assignment.strategy_version}</td><td>{assignment.master_lot}</td><td>{assignment.multiplier}</td><td>{assignment.multiplier_min}–{assignment.multiplier_max}</td><td><span className={assignment.status === "ACTIVE" ? "status-good" : "status-muted"}>{assignment.status}</span></td></tr>
                ))}
                {!portfolio.assignments.length ? <tr><td className="empty" colSpan={5}>No assignment configured.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          <div className="panel-header"><div><h2>Managed positions <span className="badge">{portfolio.managed_positions.length}</span></h2><p>Positions attributed to your strategies.</p></div><Icon name="activity" /></div>
          <div className="table-scroll" role="region" aria-label="Managed positions" tabIndex={0}>
            <table>
              <thead><tr><th scope="col">Symbol</th><th scope="col">Side</th><th scope="col">Remaining volume</th><th scope="col">State</th><th scope="col">Source reference</th></tr></thead>
              <tbody>
                {portfolio.managed_positions.map((position) => (
                  <tr key={position.id}><td><strong>{position.symbol}</strong></td><td>{position.side}</td><td>{position.remaining_volume}</td><td><span className="status-muted">{position.status}</span></td><td><code>{position.source_position_ref}</code></td></tr>
                ))}
                {!portfolio.managed_positions.length ? <tr><td className="empty" colSpan={5}>No managed positions yet.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
        <SignalsTable signals={signals} />
        <ExecutionsTable executions={executions} />
      </main>
    </>
  );
}
