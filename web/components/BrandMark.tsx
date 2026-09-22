import Link from "next/link";

/**
 * Pre-signin brand identity (landing, login, trial, subscribe, password
 * flows). Matches the post-login TopBar's "⚡ AI-EVOLVED" mark exactly, so
 * the brand reads as one identity across the whole app.
 */
export function BrandMark({ size = "md" }: { size?: "sm" | "md" }) {
  const dim = size === "sm" ? 32 : 38;
  return (
    <Link href="/" className="brandmark" aria-label="ProTrixPlus home">
      <span
        className="brandmark-icon"
        style={{ width: dim, height: dim, fontSize: dim * 0.5 }}
      >
        ⚡
      </span>
      <span className="brandmark-text">
        <span className="brandmark-name">
          ProTrixPlus
          <span className="badge-pill brandmark-badge">AI-EVOLVED</span>
        </span>
        <span className="brandmark-tagline">TradingView to MT5 Multi-User AI Router</span>
      </span>
    </Link>
  );
}
