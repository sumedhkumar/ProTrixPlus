"use client";

import { useState } from "react";

interface RadarEntry {
  symbol: string;
  pair: string;
  sentiment: "bullish" | "neutral" | "bearish";
  regime: string;
  volatility: number;
  confidence: number;
  multiplier: string;
  desc: string;
}

const INITIAL_RADAR: RadarEntry[] = [
  {
    symbol: "XAUUSD",
    pair: "Gold / US Dollar",
    sentiment: "bullish",
    regime: "Bullish Trend Expansion",
    volatility: 78,
    confidence: 94,
    multiplier: "2X Exposure",
    desc: "Sustained institutional accumulation above $2,640 support. Higher-low structure intact on the daily.",
  },
  {
    symbol: "EURUSD",
    pair: "Euro / US Dollar",
    sentiment: "neutral",
    regime: "Volatility Squeeze Range",
    volatility: 42,
    confidence: 89,
    multiplier: "1X Exposure",
    desc: "Tight mean-reverting band between 1.0820 and 1.0875. Pre-ECB rate decision caution advised.",
  },
  {
    symbol: "US30",
    pair: "Dow Jones Index CFD",
    sentiment: "bullish",
    regime: "Momentum Breakout Active",
    volatility: 84,
    confidence: 91,
    multiplier: "2X Exposure",
    desc: "Expansion outside 20-day Donchian band. Liquid US session volume driving aggressive continuation.",
  },
  {
    symbol: "BTCUSD",
    pair: "Bitcoin Spot / CFD",
    sentiment: "bullish",
    regime: "Institutional Momentum Flow",
    volatility: 88,
    confidence: 96,
    multiplier: "1X Exposure",
    desc: "Strong ETF inflow support above $92,000. Wide ATR necessitates cautious leverage sizing.",
  },
];

function sentimentLabel(s: RadarEntry["sentiment"]): string {
  return s === "bullish" ? "↗ BULLISH" : s === "bearish" ? "↘ BEARISH" : "→ NEUTRAL";
}

type ActiveTab = "market" | "sizing" | "ask";

const KELLY_TIERS = [
  {
    label: "1X Multiplier",
    tag: "Conservative",
    lots: "0.05 Lots",
    rows: [
      ["Max Drawdown VaR:", "0.24%"],
      ["Risk-of-Ruin:", "< 0.01%"],
    ],
  },
  {
    label: "2X Multiplier",
    tag: "Optimal Kelly",
    lots: "0.10 Lots",
    recommended: true,
    rows: [
      ["Max Drawdown VaR:", "0.48%"],
      ["Expected Monthly:", "+18.4%"],
    ],
  },
  {
    label: "3X Multiplier",
    tag: "Aggressive",
    lots: "0.15 Lots",
    rows: [
      ["Max Drawdown VaR:", "0.72%"],
      ["Volatility Sensitivity:", "High"],
    ],
  },
];

const CIRCUIT_BREAKERS = [
  {
    title: "Equity Floor Guard",
    value: "$22,500",
    desc: "If balance drops 10%, auto-downscale active multipliers to 1X.",
  },
  {
    title: "High-Spread Protection",
    value: "< 2.5 Pips",
    desc: "Incoming TradingView alerts auto-pause if broker spread exceeds 2.5 pips.",
  },
  {
    title: "Max Daily Loss Limit",
    value: "-$750 / Day",
    desc: "Daily loss ceiling halts new positions until next EOD settlement.",
  },
];

const SUGGESTED_PROMPTS = [
  "Audit my portfolio drawdown risk",
  "Is XAUUSD volatility safe for 2X multiplier today?",
  "Explain the TradingView webhook latency",
  "Check EURUSD upcoming news risk",
];

interface ChatMessage {
  from: "copilot" | "user";
  text: string;
  time: string;
}

function nowTime(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// Canned, keyword-matched replies. Not a real model call - see the panel's
// own "DEMO - NOT REAL AI" badge. No LLM is wired in (would need a real API
// key and a backend endpoint - a real integration decision, not a UI one).
function cannedReply(question: string): string {
  const q = question.toLowerCase();
  if (q.includes("drawdown")) {
    return "Demo response: current illustrative max drawdown VaR across your active strategies is ~0.48% at 2X exposure, within the configured Equity Floor Guard.";
  }
  if (q.includes("volatility") || q.includes("xauusd")) {
    return "Demo response: XAUUSD's illustrative volatility index is 78/100 (Bullish Trend Expansion regime) - the demo Market Radar tab has the full breakdown.";
  }
  if (q.includes("latency") || q.includes("webhook")) {
    return "Demo response: this is actually a real number - check the Webhook Telemetry tab (admin) for real signal fan-out latency, not a fabricated one.";
  }
  if (q.includes("news") || q.includes("eurusd")) {
    return "Demo response: illustrative EURUSD regime is 'Volatility Squeeze Range' with pre-ECB caution noted - no real news feed is wired in yet.";
  }
  return "Demo response: this chat has no real LLM behind it yet (Phase 9, not in the PRD) - replies are canned, not generated.";
}

export function AiCopilotPanel({ displayName, accountBalance }: { displayName: string; accountBalance: string }) {
  const [radar, setRadar] = useState(INITIAL_RADAR);
  const [spinning, setSpinning] = useState(false);
  const [tab, setTab] = useState<ActiveTab>("market");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      from: "copilot",
      text: `Welcome, ${displayName.split(" ")[0]}. I am your ProTrix AI Execution & Risk Copilot (demo). I continuously monitor TradingView signals, MT5 bridge latencies, volatility regimes, and your account equity ($${accountBalance}) - in this build, all of that is illustrative, not live. How can I help?`,
      time: nowTime(),
    },
  ]);
  const [draft, setDraft] = useState("");

  function refresh() {
    setSpinning(true);
    setTimeout(() => {
      setRadar((prev) =>
        prev.map((r) => ({
          ...r,
          volatility: Math.max(20, Math.min(99, r.volatility + Math.round(Math.random() * 10 - 5))),
          confidence: Math.max(60, Math.min(99, r.confidence + Math.round(Math.random() * 6 - 3))),
        })),
      );
      setSpinning(false);
    }, 350);
  }

  function ask(question: string) {
    if (!question.trim()) return;
    setMessages((prev) => [
      ...prev,
      { from: "user", text: question, time: nowTime() },
      { from: "copilot", text: cannedReply(question), time: nowTime() },
    ]);
    setDraft("");
  }

  return (
    <div
      className="card"
      style={{
        background: "linear-gradient(180deg, rgba(79,125,251,0.06), rgba(155,107,242,0.02))",
        borderColor: "#262f47",
        marginTop: 20,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", marginBottom: 4 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 10,
            background: "linear-gradient(135deg, var(--accent-blue), var(--accent-purple))",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flex: "none",
            color: "#fff",
            fontSize: 18,
          }}
        >
          🤖
        </div>
        <div style={{ fontSize: 16, fontWeight: 800, display: "flex", alignItems: "center", gap: 10 }}>
          ProTrix AI Copilot &amp; Risk Intelligence
          <span className="badge-pill badge-neutral">● Live Analysis</span>
          <span className="badge-pill badge-demo">DEMO - NOT REAL AI</span>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className={tab === "market" ? "chip-btn active" : "chip-btn"} onClick={() => setTab("market")}>
            📡 Market Radar
          </button>
          <button className={tab === "sizing" ? "chip-btn active" : "chip-btn"} onClick={() => setTab("sizing")}>
            ⚖️ AI Sizing Guard
          </button>
          <button className={tab === "ask" ? "chip-btn active" : "chip-btn"} onClick={() => setTab("ask")}>
            💬 Ask Copilot
          </button>
        </div>
      </div>
      <p style={{ color: "var(--muted)", fontSize: 13, margin: "4px 0 18px 54px" }}>
        Automated market regime classification, Kelly Criterion risk sizing, and institutional
        signal audits - <strong>illustrative demo data</strong>, not a live model or market feed.
      </p>

      {tab === "market" ? (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, fontWeight: 700, color: "var(--muted)", margin: "22px 0 14px" }}>
            <span className="dot green" /> Volatility &amp; Regime Classification (demo)
            <span
              onClick={refresh}
              style={{ marginLeft: "auto", color: "var(--accent-blue)", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
            >
              {spinning ? "Refreshing..." : "↻ Refresh Radar"}
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 14 }}>
            {radar.map((r) => (
              <div key={r.symbol} className="card">
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                  <div style={{ fontSize: 15, fontWeight: 800 }}>{r.symbol}</div>
                  <span className={`badge-sentiment ${r.sentiment}`}>{sentimentLabel(r.sentiment)}</span>
                </div>
                <div style={{ fontSize: 11.5, color: "var(--dim)", marginBottom: 10 }}>{r.pair}</div>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>{r.regime}</div>

                <div className="stat-sub" style={{ borderTop: "none", paddingTop: 0 }}>
                  <span>Volatility Index</span>
                  <b>{r.volatility}/100</b>
                </div>
                <div className={`meter ${r.volatility >= 65 ? "orange" : "green"}`}>
                  <span style={{ width: `${r.volatility}%` }} />
                </div>

                <div className="stat-sub" style={{ borderTop: "none", paddingTop: 0 }}>
                  <span>AI Confidence:</span>
                  <b>{r.confidence}%</b>
                </div>
                <div className="stat-sub" style={{ borderTop: "none", paddingTop: 4, marginBottom: 10 }}>
                  <span>Rec. Multiplier:</span>
                  <span className="mult-badge">{r.multiplier}</span>
                </div>
                <div style={{ fontSize: 11.5, lineHeight: 1.5, color: "var(--dim)" }}>{r.desc}</div>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {tab === "sizing" ? (
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginTop: 20 }}>
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
              <div>
                <div style={{ fontWeight: 800, fontSize: 14 }}>ProTrix Dynamic Kelly Exposure Model</div>
                <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 4, maxWidth: 380 }}>
                  Calculated against your illustrative account balance of ${accountBalance} and a
                  demo strategy win rate (68%). <strong>Not a real Kelly calculation.</strong>
                </p>
              </div>
              <span className="badge-pill badge-blue">Optimal: 2X Multiplier</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginTop: 16 }}>
              {KELLY_TIERS.map((tier) => (
                <div
                  key={tier.label}
                  className="card"
                  style={tier.recommended ? { borderColor: "var(--accent-blue)" } : undefined}
                >
                  {tier.recommended ? (
                    <div style={{ textAlign: "center", marginBottom: 6 }}>
                      <span className="badge-pill badge-blue">AI RECOMMENDED</span>
                    </div>
                  ) : null}
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, fontWeight: 700 }}>
                    {tier.label}
                    <span className="badge-pill badge-neutral">{tier.tag}</span>
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 800, margin: "8px 0" }}>{tier.lots}</div>
                  {tier.rows.map(([k, v]) => (
                    <div key={k} className="stat-sub" style={{ borderTop: "none", paddingTop: 0, fontSize: 11.5 }}>
                      <span>{k}</span>
                      <b>{v}</b>
                    </div>
                  ))}
                </div>
              ))}
            </div>

            <p style={{ color: "var(--dim)", fontSize: 12, marginTop: 14 }}>
              Automatically aligns your active strategy multipliers with the optimal 2X Kelly
              fraction.
            </p>
            <button className="btn-primary" disabled title="Demo only - not wired to real sizing">
              ✨ Apply 2X Kelly Sizing
            </button>
          </div>

          <div className="card">
            <div className="card-title" style={{ marginBottom: 12 }}>
              🛡 Automated Circuit Breakers
            </div>
            {CIRCUIT_BREAKERS.map((b) => (
              <div key={b.title} style={{ marginBottom: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700 }}>
                  {b.title}
                  <span style={{ color: "var(--warn)" }}>{b.value}</span>
                </div>
                <div style={{ color: "var(--dim)", fontSize: 11.5, marginTop: 2 }}>{b.desc}</div>
              </div>
            ))}
            <div style={{ fontSize: 11.5, color: "var(--dim)", display: "flex", alignItems: "center", gap: 6 }}>
              <span className="dot green" /> Illustrative only - not wired to real position data
            </div>
          </div>
        </div>
      ) : null}

      {tab === "ask" ? (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8 }}>Suggested inquiries:</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            {SUGGESTED_PROMPTS.map((p) => (
              <button key={p} className="secondary" onClick={() => ask(p)}>
                {p}
              </button>
            ))}
          </div>

          <div className="card" style={{ display: "grid", gap: 12, maxHeight: 320, overflowY: "auto" }}>
            {messages.map((m, i) => (
              <div key={i} style={{ alignSelf: m.from === "user" ? "flex-end" : "flex-start", maxWidth: "85%" }}>
                {m.from === "copilot" ? (
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--dim)", marginBottom: 4 }}>
                    <span>🤖 ProTrix AI Copilot (demo)</span>
                    <span>{m.time}</span>
                  </div>
                ) : null}
                <div
                  style={{
                    background: m.from === "user" ? "var(--accent-blue)" : "var(--bg)",
                    color: m.from === "user" ? "#05070d" : "var(--fg)",
                    border: m.from === "user" ? "none" : "1px solid var(--panel-border)",
                    borderRadius: 10,
                    padding: "10px 12px",
                    fontSize: 13,
                  }}
                >
                  {m.text}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask(draft)}
              placeholder="Ask ProTrix AI about strategy performance, news impact, MT5 latency, or sizing..."
              style={{ flex: 1 }}
            />
            <button className="btn-primary" onClick={() => ask(draft)}>
              Ask AI
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
