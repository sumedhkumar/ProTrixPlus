import Link from "next/link";

import type { SubscriptionStatusView } from "@/lib/api";

function pillColor(sub: SubscriptionStatusView): string {
  if (sub.in_grace || sub.is_expired) return "var(--bad)";
  if (sub.days_remaining !== null && sub.days_remaining <= 3) return "var(--warn)";
  return "var(--ok)";
}

export function SubscriptionCountdownPill({
  subscription,
}: {
  subscription: SubscriptionStatusView | null;
}) {
  if (!subscription || subscription.days_remaining === null) return null;
  const color = pillColor(subscription);
  const label = subscription.in_grace
    ? "Subscription expired"
    : `${subscription.days_remaining} day${subscription.days_remaining === 1 ? "" : "s"} left`;

  return (
    <span className="pill" title={`Plan: ${subscription.package ?? "-"}`}>
      <span className="dot" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
      {label}
    </span>
  );
}

export function SubscriptionGraceBanner({
  subscription,
}: {
  subscription: SubscriptionStatusView;
}) {
  const graceEnds = subscription.grace_ends_at
    ? new Date(subscription.grace_ends_at).toLocaleString()
    : "soon";

  return (
    <div className="card subscription-grace-banner">
      <div>
        <span className="badge-pill badge-warn" style={{ marginBottom: 8, display: "inline-flex" }}>
          Subscription expired
        </span>
        <p style={{ margin: 0, fontSize: 13, color: "var(--muted)" }}>
          Your plan expired on {subscription.end ? new Date(subscription.end).toLocaleDateString() : "-"}.
          Renew by <strong style={{ color: "var(--fg)" }}>{graceEnds}</strong> to keep dashboard access.
        </p>
      </div>
      <Link href="/subscribe?renew=true" className="btn-primary" style={{ padding: "10px 16px" }}>
        Renew Now →
      </Link>
    </div>
  );
}
