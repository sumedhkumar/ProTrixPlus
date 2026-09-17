import type { ExecutionView } from "@/lib/api";
import { Icon } from "@/components/Icon";

export function ExecutionsTable({ executions }: { executions: ExecutionView[] }) {
  return (
    <div className="panel">
      <div className="panel-header"><div><h2>Executions <span className="badge">{executions.length}</span></h2><p>Order status, broker references, and execution latency.</p></div><Icon name="activity" /></div>
      {executions.length === 0 ? (
        <div className="empty-state" data-testid="executions-empty">
          <Icon name="activity" size={25} /><strong>No executions yet</strong><p>Once an eligible signal is processed, follow its execution status here.</p>
        </div>
      ) : (
        <div className="table-scroll" role="region" aria-label="Executions" tabIndex={0}>
          <table data-testid="executions-table">
            <thead>
              <tr>
                <th scope="col">Signal</th>
                <th scope="col">User</th>
                <th scope="col">Symbol</th>
                <th scope="col">Target</th>
                <th scope="col">Lot size</th>
                <th scope="col">Adapter</th>
                <th scope="col">State</th>
                <th scope="col">Ticket</th>
                <th scope="col">Deal</th>
                <th scope="col">Reconciliations</th>
                <th scope="col">Latency ms (dispatch / ack / fill)</th>
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
