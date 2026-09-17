const INVOICES = [
  {
    id: "INV-2026-0914-01",
    period: "2026-09-14",
    strategy: "Supertrend Alpha Pro",
    profit: "+$1,440.00",
    rate: "20%",
    fee: "$288.00",
    status: "SETTLED",
  },
  {
    id: "INV-2026-0914-03",
    period: "2026-09-14",
    strategy: "EMA Ribbon Trend Catcher",
    profit: "+$430.00",
    rate: "10%",
    fee: "$43.00",
    status: "INVOICED",
  },
];

export default function SettlementPage() {
  return (
    <>
      <h1>
        My Daily EOD Profit-Share Settlement Ledger <span className="badge-pill badge-demo">DEMO</span>
      </h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Illustrative data only - the real settlement formula (gross vs. net-of-fees, per-trade vs.
        daily-aggregate) hasn&apos;t been confirmed yet (docs/FULL-BUILD-PLAN.md open question
        #5). Nothing below reflects a real calculation.
      </p>

      <div className="stat-grid" style={{ marginBottom: 20 }}>
        <div className="card">
          <div className="card-title">Total Realized Strategy Profits</div>
          <div className="stat-value green">+$1,870.00</div>
          <div className="stat-sub">
            <span>Across 2 settlement batches</span>
          </div>
        </div>
        <div className="card">
          <div className="card-title">Total Invoiced Platform Fees</div>
          <div className="stat-value">$331.00</div>
          <div className="stat-sub">
            <span>High-water / net profit billing</span>
          </div>
        </div>
        <div className="card">
          <div className="card-title">Settled / Paid Volume</div>
          <div className="stat-value">$288.00</div>
          <div className="stat-sub">
            <span>Audit-reconciled with MT5 tickets</span>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <span className="card-title">Itemized settlement statements</span>
          <span className="badge-pill badge-neutral">{INVOICES.length} invoices</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Period date</th>
                <th>Strategy</th>
                <th>Realized profit</th>
                <th>Fee rate</th>
                <th>Platform fee</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {INVOICES.map((inv) => (
                <tr key={inv.id}>
                  <td>
                    <code>{inv.id}</code>
                  </td>
                  <td>{inv.period}</td>
                  <td>{inv.strategy}</td>
                  <td style={{ color: "var(--ok)" }}>{inv.profit}</td>
                  <td>{inv.rate}</td>
                  <td>{inv.fee}</td>
                  <td>
                    <span className={`badge-pill ${inv.status === "SETTLED" ? "badge-green" : "badge-warn"}`}>
                      {inv.status}
                    </span>
                  </td>
                  <td>
                    <button className="secondary" disabled title="Demo only">
                      View statement
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
