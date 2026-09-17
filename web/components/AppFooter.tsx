const TICKS = ["AI Regime (demo)", "Idempotent", "Kelly Exposure (demo)", "EOD Settlement (demo)"];

export function AppFooter() {
  return (
    <footer
      style={{
        maxWidth: 1280,
        margin: "28px auto 0",
        padding: "16px 20px 28px",
        display: "flex",
        flexWrap: "wrap",
        gap: 10,
        justifyContent: "space-between",
        alignItems: "center",
        color: "var(--dim)",
        fontSize: 11.5,
      }}
    >
      <span>ProTrixPlus AI • TradingView to MetaTrader 5 Multi-User Autonomous Execution</span>
      <span style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
        {TICKS.map((t) => (
          <span key={t}>{t}</span>
        ))}
      </span>
    </footer>
  );
}
