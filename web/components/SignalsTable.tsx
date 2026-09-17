import type { SignalView } from "@/lib/api";
import { Icon } from "@/components/Icon";

export function SignalsTable({ signals }: { signals: SignalView[] }) {
  return (
    <div className="panel">
      <div className="panel-header"><div><h2>Signals <span className="badge">{signals.length}</span></h2><p>Accepted alerts and their execution intents.</p></div><Icon name="signal" /></div>
      {signals.length === 0 ? (
        <div className="empty-state" data-testid="signals-empty">
          <Icon name="signal" size={25} /><strong>Waiting for the first signal</strong><p>Accepted TradingView alerts will appear here with their execution details.</p>
        </div>
      ) : (
        <div className="table-scroll" role="region" aria-label="Signals" tabIndex={0}>
          <table data-testid="signals-table">
            <thead>
              <tr>
                <th scope="col">Signal ID</th>
                <th scope="col">Strategy</th>
                <th scope="col">Action</th>
                <th scope="col">Symbol</th>
                <th scope="col">Timeframe</th>
                <th scope="col">Accepted (UTC)</th>
                <th scope="col">Intents</th>
                <th scope="col">Payload hash</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <tr key={s.id} data-testid="signal-row">
                  <td>{s.signal_id}</td>
                  <td>
                    {s.strategy_key}@{s.strategy_version}
                  </td>
                  <td>{s.action}</td>
                  <td>{s.symbol}</td>
                  <td>{s.timeframe}</td>
                  <td>{s.accepted_at}</td>
                  <td>{s.intent_count}</td>
                  <td>
                    <code>{s.payload_hash.slice(0, 22)}…</code>
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
