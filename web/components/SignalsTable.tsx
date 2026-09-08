import type { SignalView } from "@/lib/api";

export function SignalsTable({ signals }: { signals: SignalView[] }) {
  return (
    <div className="panel">
      <h2>Signals</h2>
      {signals.length === 0 ? (
        <div className="empty" data-testid="signals-empty">
          No signals yet. Post one with the simulator.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table data-testid="signals-table">
            <thead>
              <tr>
                <th>signal_id</th>
                <th>strategy</th>
                <th>action</th>
                <th>symbol</th>
                <th>tf</th>
                <th>accepted_at (UTC)</th>
                <th>intents</th>
                <th>payload hash</th>
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
