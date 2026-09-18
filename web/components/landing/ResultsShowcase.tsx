// Illustrative only - there is no aggregated real-performance/track-record
// model in the platform yet (results are computed per-execution, not rolled
// up). Always shown with a DEMO tag, same convention as
// StrategyMarketplaceCard's "AI Regime Fitness" stats.
const RESULTS = [
  { strategy: "Trend Rider", timeframe: "15m", winRate: "63.4%", profitFactor: "1.82", trades: 214 },
  { strategy: "Momentum Breakout", timeframe: "1h", winRate: "58.9%", profitFactor: "1.61", trades: 176 },
  { strategy: "Mean Reversion", timeframe: "5m", winRate: "67.2%", profitFactor: "1.94", trades: 301 },
];

export function ResultsShowcase() {
  return (
    <section className="landing-section" id="results">
      <div className="landing-section-head">
        <h2>
          Strategy Results{" "}
          <span className="badge-pill badge-demo" style={{ verticalAlign: "middle" }}>
            DEMO
          </span>
        </h2>
        <p>
          Illustrative performance figures - your own execution history, computed from your real
          fills, is available on your dashboard once you sign in.
        </p>
      </div>

      <div className="stat-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        {RESULTS.map((r) => (
          <div key={r.strategy} className="card">
            <div className="card-head">
              <span className="card-title">{r.strategy}</span>
              <span className="badge-pill badge-neutral">{r.timeframe}</span>
            </div>
            <div className="stat-value green">{r.winRate}</div>
            <div className="stat-sub-cols">
              <div>
                <div>{r.profitFactor}</div>
                <div>Profit factor</div>
              </div>
              <div>
                <div>{r.trades}</div>
                <div>Trades tracked</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
