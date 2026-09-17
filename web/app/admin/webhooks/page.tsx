import { apiFetch, type OpsSummary, type SignalView } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function WebhooksPage() {
  const token = getToken()!;
  const [signals, opsSummary] = await Promise.all([
    apiFetch<SignalView[]>("/api/v1/signals", token),
    apiFetch<OpsSummary>("/api/v1/admin/ops-summary", token),
  ]);

  return (
    <>
      <h1>TradingView Webhook Audit &amp; Fan-Out Telemetry</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Every inbound signal, idempotency status, and how many clients it fanned out to. A
        per-dispatch raw payload / per-client MT5-bridge log (like the reference mockup&apos;s
        detailed drill-down) isn&apos;t built yet - what&apos;s below is real, not simulated.
      </p>

      <div className="stat-grid" style={{ marginBottom: 20 }}>
        <div className="card">
          <div className="card-title">Total signals</div>
          <div className="stat-value">{opsSummary.total_signals}</div>
        </div>
        <div className="card">
          <div className="card-title">Total executions</div>
          <div className="stat-value">{opsSummary.total_executions}</div>
        </div>
        <div className="card">
          <div className="card-title">Stuck in UNKNOWN</div>
          <div
            className="stat-value"
            style={{ color: opsSummary.stuck_unknown_count > 0 ? "var(--bad)" : "var(--fg)" }}
          >
            {opsSummary.stuck_unknown_count}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Revoked entitlements</div>
          <div className="stat-value">{opsSummary.revoked_assignments}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <span className="card-title">Inbound signal log</span>
        </div>
        {signals.length === 0 ? (
          <div className="empty">No signals received yet.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Signal ID</th>
                  <th>Strategy</th>
                  <th>Action</th>
                  <th>Symbol</th>
                  <th>Timeframe</th>
                  <th>Dispatched to</th>
                  <th>Accepted at</th>
                  <th>Payload hash</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <code>{s.signal_id}</code>
                    </td>
                    <td>
                      {s.strategy_key}@{s.strategy_version}
                    </td>
                    <td>
                      <span className={`badge-pill ${s.action === "BUY" ? "badge-green" : "badge-bad"}`}>
                        {s.action}
                      </span>
                    </td>
                    <td>{s.symbol}</td>
                    <td>{s.timeframe}</td>
                    <td>{s.intent_count} client(s)</td>
                    <td>{new Date(s.accepted_at).toLocaleString()}</td>
                    <td>
                      <code>{s.payload_hash.slice(0, 18)}…</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
