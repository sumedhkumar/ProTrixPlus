"use client";

import { useMemo, useState } from "react";

import type { ExecutionView } from "@/lib/api";

const FILTERS = ["ALL", "FILLED", "CLOSED", "REJECTED"] as const;
type Filter = (typeof FILTERS)[number];

// A "closed" position is a real, derivable fact (a FILLED execution that has
// since received an exit_price/realized_pnl) - not a fabricated status. The
// raw backend state (protrix_contracts.lifecycle.ExecutionState) has no
// separate CLOSED value; every other real state is shown as-is.
function displayStatus(e: ExecutionView): string {
  if (e.state === "FILLED" && e.exit_price !== null) return "CLOSED";
  return e.state;
}

function statusBadgeClass(status: string): string {
  if (status === "FILLED" || status === "CLOSED") return "badge-green";
  if (status === "REJECTED") return "badge-bad";
  if (status === "UNKNOWN" || status === "RECONCILED") return "badge-warn";
  return "badge-neutral";
}

function sideBadgeClass(action: string): string {
  if (action === "BUY") return "badge-green";
  if (action === "SELL") return "badge-bad";
  return "badge-blue"; // CLOSE / PARTIAL_CLOSE / MODIFY_SLTP / EMERGENCY_CLOSE
}

// "mock" is the deterministic simulator (see worker/app/adapters/mock.py) -
// every fill it produces is fake, never a real broker order. Anything else
// (metaapi, the native mt5 adapter) is a real transport.
function isRealAdapter(adapter: string): boolean {
  return adapter !== "mock";
}

// last_error stores the exact technical detail from the adapter/broker (see
// worker/app/execution.py) - correct, but not something a client should have
// to parse. This translates the real, known cases into plain English; the
// raw string always stays visible underneath, never hidden, just
// de-prioritized (nothing here fabricates a reason - unrecognized errors
// fall back to a generic line rather than guessing).
function humanizeError(raw: string): string {
  if (raw.includes("reason=trading_disabled")) {
    return "Live trading is currently turned off for this connection.";
  }
  if (raw.includes("reason=management_action_not_yet_supported")) {
    return "Closing or adjusting an existing position isn't supported yet - only new trades.";
  }
  if (raw.includes("no_metaapi_account_configured") || raw.includes("account connected")) {
    return "This account isn't linked to a broker yet.";
  }
  if (raw.includes("MARKET_CLOSED")) {
    return "The market for this symbol is closed right now - this will succeed once trading hours reopen.";
  }
  if (raw.includes("UNKNOWN_SYMBOL")) {
    return "This symbol isn't available on the connected broker account.";
  }
  if (raw.includes("ValidationError")) {
    return "The order request was malformed and rejected before reaching the broker - no trade was placed.";
  }
  if (raw.includes("did not complete") || raw.toLowerCase().includes("timeout")) {
    return "We couldn't confirm this order in time - it's being double-checked against the broker.";
  }
  const messageMatch = raw.match(/message=([^;]+)/);
  if (messageMatch?.[1]) return `The broker said: "${messageMatch[1].trim()}"`;
  return "This order was rejected. See technical details below.";
}

function toCsv(rows: ExecutionView[]): string {
  const header = [
    "Ticket",
    "Strategy",
    "Symbol",
    "Side",
    "Volume",
    "Fill Price",
    "Close Price",
    "Latency (ms)",
    "Source",
    "Status",
    "Rejection Reason",
    "Realized P&L",
    "Timestamp",
  ];
  const lines = rows.map((e) =>
    [
      e.ticket_id ?? "",
      e.strategy_key,
      e.symbol,
      e.action,
      e.computed_lot,
      e.entry_price ?? "",
      e.exit_price ?? "",
      e.latency_fill_ms ?? "",
      isRealAdapter(e.adapter) ? "LIVE" : "DEMO",
      displayStatus(e),
      e.last_error ?? "",
      e.realized_pnl ?? "",
      e.updated_at,
    ]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(","),
  );
  return [header.join(","), ...lines].join("\n");
}

export function ExecutionHistoryTable({
  executions,
  title,
  showClientColumn,
}: {
  executions: ExecutionView[];
  title: string;
  showClientColumn: boolean;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [strategyFilter, setStrategyFilter] = useState("ALL");
  const [tooltip, setTooltip] = useState<{
    friendly: string;
    raw: string;
    top: number;
    left: number;
  } | null>(null);

  // position:fixed (not absolute) and computed from the real element - the
  // table's own overflow-x:auto wrapper clips a Y-overflowing absolute child
  // too (overflow-x:auto implicitly makes overflow-y clipping as well), so a
  // tooltip nested inside it can get cut off or never render. Same fix as
  // the header's Execution Engine popover.
  function showTooltip(el: HTMLElement, raw: string) {
    const rect = el.getBoundingClientRect();
    setTooltip({ friendly: humanizeError(raw), raw, top: rect.bottom + 6, left: rect.left });
  }

  const strategyOptions = useMemo(
    () => Array.from(new Set(executions.map((e) => e.strategy_key))).sort(),
    [executions],
  );

  const filtered = useMemo(() => {
    return executions.filter((e) => {
      if (filter !== "ALL" && displayStatus(e) !== filter) return false;
      if (strategyFilter !== "ALL" && e.strategy_key !== strategyFilter) return false;
      if (!query) return true;
      const haystack = `${e.ticket_id ?? ""} ${e.symbol} ${e.strategy_key} ${e.user_display_name}`.toLowerCase();
      return haystack.includes(query.toLowerCase());
    });
  }, [executions, query, filter, strategyFilter]);

  function exportCsv() {
    const csv = toCsv(filtered);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `protrixplus-executions-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">{title}</span>
        <button type="button" className="secondary" onClick={exportCsv} disabled={filtered.length === 0}>
          ⬇ Export CSV Audit
        </button>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <input
          placeholder="Search ticket #, symbol, strategy, or client..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ flex: 1, minWidth: 220 }}
        />
        <select value={strategyFilter} onChange={(e) => setStrategyFilter(e.target.value)}>
          <option value="ALL">All Strategies</option>
          {strategyOptions.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <div style={{ display: "flex", gap: 6 }}>
          {FILTERS.map((f) => (
            <button
              key={f}
              className={filter === f ? "btn-primary" : "secondary"}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="empty" data-testid="executions-empty">
          No executions match.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table data-testid="executions-table">
            <thead>
              <tr>
                <th>Ticket #</th>
                <th>Strategy</th>
                {showClientColumn ? <th>Client</th> : null}
                <th>Symbol</th>
                <th>Side</th>
                <th>Volume</th>
                <th>Fill Price</th>
                <th>Close Price</th>
                <th>Latency</th>
                <th>Source</th>
                <th>Status</th>
                <th>Realized P&amp;L</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => {
                const status = displayStatus(e);
                return (
                <tr key={e.id} data-testid="execution-row">
                  <td>
                    <code>{e.ticket_id ?? "—"}</code>
                  </td>
                  <td>{e.strategy_key}</td>
                  {showClientColumn ? <td>{e.user_display_name}</td> : null}
                  <td>{e.symbol}</td>
                  <td>
                    <span className={`badge-pill ${sideBadgeClass(e.action)}`}>{e.action}</span>
                  </td>
                  <td>{e.computed_lot}L</td>
                  <td>{e.entry_price ?? "—"}</td>
                  <td>{e.exit_price ?? "—"}</td>
                  <td>{e.latency_fill_ms ?? "—"}ms</td>
                  <td>
                    {isRealAdapter(e.adapter) ? (
                      <span className="badge-pill badge-green" title={`adapter: ${e.adapter}`}>
                        LIVE
                      </span>
                    ) : (
                      <span className="badge-pill badge-demo" title="simulated fill - no real broker order">
                        DEMO
                      </span>
                    )}
                  </td>
                  <td data-testid="execution-state">
                    <span
                      className={`badge-pill ${statusBadgeClass(status)}`}
                      style={e.last_error ? { cursor: "help" } : undefined}
                      onMouseEnter={(ev) =>
                        e.last_error ? showTooltip(ev.currentTarget, e.last_error) : undefined
                      }
                      onMouseLeave={() => setTooltip(null)}
                    >
                      {status}
                      {e.last_error ? " ⓘ" : ""}
                    </span>
                  </td>
                  <td style={{ color: e.realized_pnl ? "var(--ok)" : "var(--dim)" }}>
                    {e.realized_pnl ?? "—"}
                  </td>
                  <td>{new Date(e.updated_at).toLocaleString()}</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {tooltip ? (
        <div
          style={{
            position: "fixed",
            top: tooltip.top,
            left: tooltip.left,
            zIndex: 300,
            maxWidth: 340,
            background: "var(--panel, #11151f)",
            border: "1px solid var(--panel-border)",
            borderRadius: 8,
            padding: "10px 12px",
            fontSize: 12,
            color: "var(--fg)",
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            pointerEvents: "none",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{tooltip.friendly}</div>
          <div style={{ color: "var(--dim)", fontSize: 10.5, wordBreak: "break-word" }}>
            {tooltip.raw}
          </div>
        </div>
      ) : null}
    </div>
  );
}
