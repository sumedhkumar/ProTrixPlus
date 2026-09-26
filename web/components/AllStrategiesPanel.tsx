"use client";

import { useMemo, useState } from "react";

import type { LiveBalance, Mt5ConnectionView, MyAssignmentView, StrategyView } from "@/lib/api";

import { StrategyMarketplaceCard } from "./StrategyMarketplaceCard";

const INITIAL_VISIBLE = 6;

export function AllStrategiesPanel({
  strategies,
  myAssignments,
  mt5Connection,
  liveBalance,
}: {
  strategies: StrategyView[];
  myAssignments: MyAssignmentView[];
  mt5Connection: Mt5ConnectionView | null;
  liveBalance: LiveBalance;
}) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);

  const byStrategyId = useMemo(
    () => new Map(myAssignments.map((a) => [a.strategy_id, a])),
    [myAssignments],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return strategies;
    return strategies.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.strategy_key.toLowerCase().includes(q) ||
        (s.symbol ?? "").toLowerCase().includes(q),
    );
  }, [strategies, query]);

  const visible = expanded ? filtered : filtered.slice(0, INITIAL_VISIBLE);
  const hiddenCount = filtered.length - visible.length;

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="card-head" style={{ marginBottom: 16 }}>
        <span className="card-title">All Strategies</span>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="badge-pill badge-neutral">{strategies.length} available</span>
          <div style={{ position: "relative" }}>
            <span
              aria-hidden
              style={{
                position: "absolute",
                left: 10,
                top: "50%",
                transform: "translateY(-50%)",
                fontSize: 13,
                color: "var(--muted)",
                pointerEvents: "none",
              }}
            >
              🔍
            </span>
            <input
              type="search"
              placeholder="Search strategies..."
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setExpanded(false);
              }}
              style={{ width: 260, padding: "8px 10px 8px 30px", fontSize: 13.5 }}
            />
          </div>
        </div>
      </div>

      {strategies.length === 0 ? (
        <div className="empty">No strategies published yet.</div>
      ) : filtered.length === 0 ? (
        <div className="empty">No strategies match &quot;{query}&quot;.</div>
      ) : (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
              gap: 14,
            }}
          >
            {visible.map((s) => (
              <StrategyMarketplaceCard
                key={s.id}
                strategy={s}
                assignment={byStrategyId.get(s.id)}
                mt5Connection={mt5Connection}
                liveBalance={liveBalance}
              />
            ))}
          </div>

          {hiddenCount > 0 ? (
            <div style={{ display: "flex", justifyContent: "center", marginTop: 16 }}>
              <button type="button" className="secondary" onClick={() => setExpanded(true)}>
                See more ({hiddenCount} more)
              </button>
            </div>
          ) : expanded && filtered.length > INITIAL_VISIBLE ? (
            <div style={{ display: "flex", justifyContent: "center", marginTop: 16 }}>
              <button type="button" className="secondary" onClick={() => setExpanded(false)}>
                Show less
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
