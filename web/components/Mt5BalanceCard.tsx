"use client";

import { useState } from "react";

import type { Mt5ConnectionView } from "@/lib/api";

import { Mt5ConnectionModal } from "./Mt5ConnectionModal";

export function Mt5BalanceCard({
  connection,
  displayName,
  demoBalance,
}: {
  connection: Mt5ConnectionView | null;
  displayName: string;
  demoBalance: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="card">
        <div className="card-head">
          <span className="card-title">MT5 Balance</span>
          <button type="button" className="card-link" onClick={() => setOpen(true)}>
            Config
          </button>
        </div>
        <div className="stat-value">
          ${demoBalance} <span className="badge-pill badge-demo">DEMO</span>
        </div>
        {connection ? (
          <div className="stat-sub">
            <span>
              {connection.broker_server} / {connection.login}
            </span>
            <span
              className={`badge-pill ${connection.status === "CONNECTED" ? "badge-green" : "badge-warn"}`}
              title="This status badge is real; the dollar figure above is not"
            >
              {connection.status}
            </span>
          </div>
        ) : (
          <div className="stat-sub">
            <span>No broker connected - click Config to set up</span>
          </div>
        )}
      </div>

      {open ? (
        <Mt5ConnectionModal
          connection={connection}
          displayName={displayName}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}
