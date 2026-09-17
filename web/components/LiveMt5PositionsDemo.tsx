"use client";

// Illustrative only - real open-position data requires a live MetaApi broker
// connection, which doesn't exist yet. A "Close" action here would place a
// real order if it worked, so it's disabled, not just cosmetically styled.
const DEMO_POSITIONS = [
  {
    ticket: "#8940280",
    strategy: "Supertrend Alpha Pro",
    symbol: "XAUUSD",
    side: "BUY" as const,
    volume: "0.1L",
    openPrice: "2645.2",
    sl: "2632",
    tp: "2668",
    latency: "36ms",
    floatingPnl: "+$320.00",
  },
];

export function LiveMt5PositionsDemo() {
  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="card-head">
        <span className="card-title">
          <span className="dot green" /> Live MT5 Open Positions ({DEMO_POSITIONS.length}){" "}
          <span className="badge-pill badge-demo">DEMO</span>
        </span>
        <span style={{ fontSize: 13 }}>
          Attributable P&amp;L: <span style={{ color: "var(--ok)", fontWeight: 700 }}>+$320.00</span>
        </span>
      </div>
      <p style={{ color: "var(--dim)", fontSize: 12, marginBottom: 14 }}>
        Requires a live MetaApi broker connection to be real - the &ldquo;Close&rdquo; action is
        disabled on purpose.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Ticket #</th>
              <th>Strategy</th>
              <th>Symbol</th>
              <th>Type</th>
              <th>Volume</th>
              <th>Open price</th>
              <th>SL / TP</th>
              <th>Latency</th>
              <th>Floating P&amp;L</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {DEMO_POSITIONS.map((p) => (
              <tr key={p.ticket}>
                <td>
                  <code>{p.ticket}</code>
                </td>
                <td>{p.strategy}</td>
                <td>{p.symbol}</td>
                <td>
                  <span className={`badge-pill ${p.side === "BUY" ? "badge-green" : "badge-bad"}`}>
                    {p.side}
                  </span>
                </td>
                <td>{p.volume}</td>
                <td>{p.openPrice}</td>
                <td>
                  {p.sl} / {p.tp}
                </td>
                <td>{p.latency}</td>
                <td style={{ color: "var(--ok)", fontWeight: 700 }}>{p.floatingPnl}</td>
                <td>
                  <button className="secondary" disabled title="Demo only - needs a real MetaApi connection">
                    Close
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
