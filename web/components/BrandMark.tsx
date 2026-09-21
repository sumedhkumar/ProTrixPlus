import Link from "next/link";

/**
 * Pre-signin brand identity (landing, login, trial, subscribe, password
 * flows). Deliberately distinct from the post-login TopBar's "⚡ AI-EVOLVED"
 * mark - this is its own visual language, not a reuse of it.
 */
export function BrandMark({ size = "md" }: { size?: "sm" | "md" }) {
  const dim = size === "sm" ? 32 : 38;
  return (
    <Link href="/" className="brandmark" aria-label="ProTrixPlus home">
      <span className="brandmark-icon" style={{ width: dim, height: dim }}>
        <svg viewBox="0 0 24 24" width={dim * 0.56} height={dim * 0.56} fill="none">
          <path
            d="M3 16 L9 10 L13 14 L20 6"
            stroke="white"
            strokeWidth="2.3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path d="M20 6 L14.5 6.5" stroke="white" strokeWidth="2.3" strokeLinecap="round" />
          <path d="M20 6 L19.3 11.3" stroke="white" strokeWidth="2.3" strokeLinecap="round" />
        </svg>
      </span>
      <span className="brandmark-text">
        <span className="brandmark-name">
          ProTrixPlus
          <span className="badge-pill brandmark-badge">REAL-TIME EXECUTION</span>
        </span>
        <span className="brandmark-tagline">TradingView to MT5 Multi-User Router</span>
      </span>
    </Link>
  );
}
