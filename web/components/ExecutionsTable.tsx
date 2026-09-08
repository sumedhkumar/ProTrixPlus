import type { ExecutionView } from "@/lib/api";

export function ExecutionsTable({ executions }: { executions: ExecutionView[] }) {
  return (
    <div className="panel">
      <h2>Executions</h2>
      {executions.length === 0 ? (
        <div className="empty" data-testid="executions-empty">
          No executions yet.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table data-testid="executions-table">
            <thead>
              <tr>
                <th>signal</th>
                <th>user</th>
                <th>symbol</th>
                <th>target</th>
                <th>lot</th>
                <th>adapter</th>
                <th>state</th>
                <th>ticket</th>
                <th>deal</th>
                <th>reconciles</th>
                <th>latency ms (disp/ack/fill)</th>
              </tr>
            </thead>
            <tbody>
              {executions.map((e) => (
                <tr key={e.id} data-testid="execution-row">
                  <td>{e.signal_ref}</td>
                  <td>{e.user_display_name}</td>
                  <td>{e.symbol}</td>
                  <td>{e.command_target}</td>
                  <td>{e.computed_lot}</td>
                  <td>{e.adapter}</td>
                  <td className={`state state-${e.state}`} data-testid="execution-state">
                    {e.state}
                  </td>
                  <td>{e.ticket_id ?? "—"}</td>
                  <td>{e.deal_id ?? "—"}</td>
                  <td>{e.reconcile_count}</td>
                  <td>
                    {e.latency_dispatch_ms ?? "—"}/{e.latency_ack_ms ?? "—"}/
                    {e.latency_fill_ms ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
