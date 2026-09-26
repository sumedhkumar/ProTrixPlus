import type { LiveBalance, Mt5ConnectionView } from "@/lib/api";

/** Read-only display now - MT5 connection setup happens only inside the
 * per-strategy Setup Wizard (after subscribing), not from a standalone
 * "Config" entry point here, so a client can't half-configure a broker
 * connection disconnected from any actual strategy subscription. */
export function Mt5BalanceCard({
  connection,
  liveBalance,
}: {
  connection: Mt5ConnectionView | null;
  liveBalance: LiveBalance;
}) {
  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">MT5 Balance</span>
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
          {liveBalance.reason ?? "Balance not available - subscribe to a strategy to connect MT5."}
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
          <span>No broker connected yet - set this up from a strategy&apos;s Setup Wizard</span>
        </div>
      )}
    </div>
  );
}
