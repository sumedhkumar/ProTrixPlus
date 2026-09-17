"use client";

import { useState } from "react";

const INVOICES = [
  { id: "INV-2026-0914-01", period: "2026-09-14", client: "Marcus Sterling", strategy: "Supertrend Alpha Pro", profit: "+$1,440.00", rate: "20%", fee: "$288.00", status: "SETTLED" },
  { id: "INV-2026-0914-02", period: "2026-09-14", client: "Elena Rostova", strategy: "Supertrend Alpha Pro", profit: "+$1,722.00", rate: "20%", fee: "$344.40", status: "SETTLED" },
  { id: "INV-2026-0914-03", period: "2026-09-14", client: "Marcus Sterling", strategy: "EMA Ribbon Trend Catcher", profit: "+$430.00", rate: "10%", fee: "$43.00", status: "INVOICED" },
  { id: "INV-2026-0914-04", period: "2026-09-14", client: "David Chen", strategy: "EMA Ribbon Trend Catcher", profit: "+$440.00", rate: "10%", fee: "$44.00", status: "PENDING" },
];

export default function AdminSettlementPage() {
  const [running, setRunning] = useState(false);

  return (
    <>
      <h1>
        EOD Profit-Share Settlement Engine <span className="badge-pill badge-demo">DEMO</span>
      </h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Illustrative data only - the settlement formula needs confirming first
        (docs/FULL-BUILD-PLAN.md open question #5) before this becomes a real daily batch job.
      </p>

      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <button
          className="btn-primary"
          disabled={running}
          onClick={() => {
            setRunning(true);
            setTimeout(() => setRunning(false), 900);
          }}
        >
          {running ? "Running..." : "▷ Run EOD Settlement Batch (demo)"}
        </button>
      </div>

      <div className="stat-grid" style={{ marginBottom: 20 }}>
        <div className="card">
          <div className="card-title">Total Client Strategy Profits Generated</div>
          <div className="stat-value green">+$4,032.00</div>
          <div className="stat-sub">
            <span>Net realized profits across all subscribers</span>
          </div>
        </div>
        <div className="card">
          <div className="card-title">Total Invoiced Platform Profit-Share</div>
          <div className="stat-value">$719.40</div>
          <div className="stat-sub">
            <span>Configurable 10% / 20% splits</span>
          </div>
        </div>
        <div className="card">
          <div className="card-title">Collected / Settled Revenue</div>
          <div className="stat-value">$632.40</div>
          <div className="stat-sub">
            <span>87.9% collection rate</span>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <span className="card-title">Master invoices ledger</span>
          <span className="badge-pill badge-neutral">{INVOICES.length} invoices</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Period date</th>
                <th>Client</th>
                <th>Strategy</th>
                <th>Realized profit</th>
                <th>Rate</th>
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
                  <td style={{ fontWeight: 700 }}>{inv.client}</td>
                  <td>{inv.strategy}</td>
                  <td style={{ color: "var(--ok)" }}>{inv.profit}</td>
                  <td>{inv.rate}</td>
                  <td>{inv.fee}</td>
                  <td>
                    <span
                      className={`badge-pill ${
                        inv.status === "SETTLED"
                          ? "badge-green"
                          : inv.status === "INVOICED"
                            ? "badge-warn"
                            : "badge-neutral"
                      }`}
                    >
                      {inv.status}
                    </span>
                  </td>
                  <td>
                    <button className="secondary" disabled title="Demo only">
                      View invoice
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
