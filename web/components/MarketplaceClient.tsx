"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Icon } from "@/components/Icon";
import type { MarketplaceOffer, StrategyEnrollmentView } from "@/lib/api";

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

interface CheckoutOrder {
  payment_order_id: string;
  razorpay_order_id: string;
  key_id: string;
  amount_usd: string;
  currency: string;
}

function money(value: string) {
  return `USD ${Number(value).toFixed(2)}`;
}

function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Unable to load Razorpay Checkout"));
    document.head.appendChild(script);
  });
}

async function marketplacePost(path: string, body: object, idempotencyKey?: string) {
  const response = await fetch("/api/marketplace", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, body, idempotencyKey }),
  });
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) throw new Error(typeof payload.error === "string" ? payload.error : "Request failed");
  return payload;
}

export function MarketplaceClient({ offers, enrollments, signedIn }: { offers: MarketplaceOffer[]; enrollments: StrategyEnrollmentView[]; signedIn: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const enrollmentByStrategy = useMemo(() => new Map(enrollments.map((enrollment) => [enrollment.strategy_id, enrollment])), [enrollments]);

  async function buy(offer: MarketplaceOffer) {
    if (!signedIn) {
      router.push("/login");
      return;
    }
    setBusy(offer.strategy_id);
    setMessage(null);
    try {
      const order = (await marketplacePost(`/api/v1/marketplace/strategies/${offer.strategy_id}/checkout`, {}, crypto.randomUUID())) as unknown as CheckoutOrder;
      await loadRazorpay();
      if (!window.Razorpay) throw new Error("Razorpay Checkout is unavailable");
      const checkout = new window.Razorpay({
        key: order.key_id,
        order_id: order.razorpay_order_id,
        amount: Math.round(Number(order.amount_usd) * 100),
        currency: order.currency,
        name: "ProtrixPlus",
        description: `${offer.name} — ${offer.duration_days} day access`,
        handler: async (payment: { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string }) => {
          try {
            await marketplacePost("/api/v1/payments/razorpay/verify", payment);
            setMessage("Payment verified. Set up the dedicated MT5 account for this strategy.");
            router.refresh();
          } catch (error) {
            setMessage(error instanceof Error ? error.message : "Payment verification failed");
          } finally {
            setBusy(null);
          }
        },
        modal: { ondismiss: () => setBusy(null) },
        theme: { color: "#36d6c6" },
      });
      checkout.open();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to start checkout");
      setBusy(null);
    }
  }

  return <section className="marketplace-shell">
    <div className="marketplace-heading"><div><h1>Find your next strategy.</h1><p>Explore automated strategies with dedicated MT5 accounts and separate escrow wallets.</p></div><div className="marketplace-rule"><Icon name="shield" size={23} /><div><strong>Every strategy. Its own account.</strong>Separate execution, wallet, and controls.</div></div></div>
    {message ? <p className="marketplace-message" role="status">{message}</p> : null}
    <div className="marketplace-toolbar"><strong>All strategies</strong><span className="badge">{offers.length}</span><span>Transparent pricing · Dedicated execution</span></div>
    <div className="marketplace-grid">
      {offers.map((offer) => {
        const enrollment = enrollmentByStrategy.get(offer.strategy_id);
        const active = enrollment?.status === "ACTIVE" && enrollment.wallet.entry_allowed;
        return <article className={`strategy-card${active ? " strategy-card-active" : ""}`} key={offer.strategy_id}>
          <div className="strategy-card-topline"><span className="strategy-icon"><Icon name="activity" size={25} /></span><span className={active ? "status-good" : "status-muted"}>{active ? "ACTIVE" : enrollment?.status.replaceAll("_", " ") ?? "AVAILABLE"}</span></div>
          <span className="strategy-key">{offer.strategy_key} / {offer.strategy_version}</span>
          <h2>{offer.name}</h2><p className="strategy-description">{offer.description || "Managed execution with isolated risk, wallet, and MT5 account routing."}</p>
          <div className="strategy-price"><strong>{money(offer.price_usd)}</strong><span>per {offer.duration_days} days</span></div>
          <dl className="strategy-terms"><div><dt>Platform fee</dt><dd>{money(offer.platform_fee_usd)}</dd></div><div><dt>Escrow credit</dt><dd className="positive">{money(offer.escrow_credit_usd)}</dd></div><div><dt>Entry safety floor</dt><dd>{money(offer.minimum_wallet_usd)}</dd></div><div><dt>Profit share</dt><dd>{(Number(offer.profit_share_rate) * 100).toFixed(0)}% of closed PnL</dd></div></dl>
          {enrollment ? <p className="strategy-enrollment-note">Current escrow: <strong>{money(enrollment.wallet.balance)}</strong>{enrollment.wallet.entry_allowed ? " — entries eligible when account is connected." : " — top up to the safety floor to resume entries."}</p> : null}
          <button disabled={busy !== null} onClick={() => void buy(offer)}>{busy === offer.strategy_id ? "Opening secure checkout…" : !signedIn ? "Sign in to activate" : enrollment ? `Renew for ${offer.duration_days} days` : "Activate strategy"}<Icon name="arrow" size={16} /></button>
          <p className="strategy-footer"><Icon name="lock" size={13} /> Checkout with Razorpay</p>
        </article>;
      })}
    </div>
    {!offers.length ? <div className="empty-state"><Icon name="layers" size={28} /><strong>New strategies are on the way</strong><p>No marketplace strategies are published yet. Check back here for available offers.</p></div> : null}
  </section>;
}
