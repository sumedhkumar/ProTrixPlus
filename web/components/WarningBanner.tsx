const TONE_STYLES = {
  warn: { color: "var(--warn)", background: "rgba(246, 166, 35, 0.08)" },
  bad: { color: "var(--bad)", background: "rgba(240, 87, 107, 0.08)" },
} as const;

/** Shared visual treatment for a non-blocking-but-important callout (e.g. a
 * strategy's minimum MT5 balance requirement) - bordered/tinted box with an
 * icon, a bold title, and a muted detail line, instead of a raw emoji +
 * plain-text paragraph. */
export function WarningBanner({
  tone = "warn",
  title,
  message,
  style,
}: {
  tone?: "warn" | "bad";
  title: string;
  message: string;
  style?: React.CSSProperties;
}) {
  const { color, background } = TONE_STYLES[tone];
  return (
    <div
      role="alert"
      style={{
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
        padding: "10px 14px",
        borderRadius: 10,
        marginBottom: 12,
        border: `1px solid ${color}`,
        background,
        ...style,
      }}
    >
      <span
        aria-hidden
        style={{
          flex: "0 0 auto",
          width: 20,
          height: 20,
          borderRadius: "50%",
          background: color,
          color: "#1a0508",
          fontSize: 12,
          fontWeight: 800,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        !
      </span>
      <div>
        <div style={{ fontWeight: 700, fontSize: 12.5, color }}>{title}</div>
        <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2, lineHeight: 1.45 }}>
          {message}
        </div>
      </div>
    </div>
  );
}
