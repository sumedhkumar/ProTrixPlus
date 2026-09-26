"use client";

import { useState } from "react";

import type { LiveBalance, Mt5ConnectionView } from "@/lib/api";

import { Mt5ConnectionModal } from "./Mt5ConnectionModal";

export function Mt5BalanceCard({
  connection,
  displayName,
  liveBalance,
}: {
  connection: Mt5ConnectionView | null;
  displayName: string;
  liveBalance: LiveBalance;
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
        {liveBalance.available ? (
          <div className="stat-value">
            ${liveBalance.balance?.toFixed(2)}{" "}
            <span className="badge-pill badge-green" title="Real balance, read from MetaApi.cloud">
              LIVE
            </span>
          </div>
        ) : (
          <div style={{ color: "var(--muted)", fontSize: 13.5 }}>
            {liveBalance.reason ?? "Balance not available - connect a live MT5 account."}
          </div>
        )}
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
