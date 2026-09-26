"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import type { LiveBalance, Mt5ConnectionView, MyAssignmentView, StrategyView } from "@/lib/api";

import { StrategyMarketplaceCard } from "./StrategyMarketplaceCard";

const INITIAL_VISIBLE = 6;
const MT5_SETUP_FEE_DISPLAY = "10.00";

export function AllStrategiesPanel({
  strategies,
  myAssignments,
  mt5Connection,
  liveBalance,
  mt5SetupFeePaid,
}: {
  strategies: StrategyView[];
  myAssignments: MyAssignmentView[];
  mt5Connection: Mt5ConnectionView | null;
  liveBalance: LiveBalance;
  mt5SetupFeePaid: boolean;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  async function payMt5SetupFee() {
    setPaying(true);
    setPayError(null);
    const res = await fetch("/api/me/mt5-setup-fee/pay", { method: "POST" });
    setPaying(false);
    if (!res.ok) {
      setPayError(`payment failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  // A REVOKED assignment isn't deleted (it stays for history/audit), but it
  // must behave as "not subscribed" here - otherwise a client who was
  // unsubscribed still sees "Update Sizing"/"Complete Setup" instead of a
  // fresh Subscribe button, as if nothing happened.
  const byStrategyId = useMemo(
    () =>
      new Map(
        myAssignments.filter((a) => a.payment_status !== "REVOKED").map((a) => [a.strategy_id, a]),
      ),
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

      {!mt5SetupFeePaid ? (
        <div
          className="card"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 14,
            flexWrap: "wrap",
            padding: "14px 16px",
            marginBottom: 16,
            background: "rgba(246, 166, 35, 0.06)",
            border: "1px solid rgba(246, 166, 35, 0.3)",
          }}
        >
          <div>
            <div style={{ fontWeight: 700, fontSize: 13.5 }}>
              🔒 Activate your account to subscribe
            </div>
            <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 4, marginBottom: 0 }}>
              A one-time ${MT5_SETUP_FEE_DISPLAY} setup fee covers the real cost of provisioning
              your MetaApi trading account - pay once, then subscribe to any strategy.
              {payError ? <span style={{ color: "var(--bad)" }}> {payError}</span> : null}
            </p>
          </div>
          <button
            type="button"
            className="btn-primary"
            disabled={paying}
            onClick={() => void payMt5SetupFee()}
            style={{ whiteSpace: "nowrap" }}
          >
            {paying ? "Processing..." : `💳 Pay $${MT5_SETUP_FEE_DISPLAY} (Demo)`}
          </button>
        </div>
      ) : null}

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
                mt5SetupFeePaid={mt5SetupFeePaid}
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
