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
      <span>ProTrixPlus • TradingView to MetaTrader 5 Multi-User Trading Automation</span>
      <span>Idempotent signal ingestion</span>
    </footer>
  );
}
