"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/Icon";

import type { StrategyEnrollmentView } from "@/lib/api";

interface CheckoutOrder {
  razorpay_order_id: string;
  key_id: string;
  amount_usd: string;
  currency: string;
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

async function post(path: string, body: object, idempotencyKey?: string) {
  const response = await fetch("/api/marketplace", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, body, idempotencyKey }),
  });
  const payload = (await response.json().catch(() => ({}))) as { error?: string };
  if (!response.ok) throw new Error(payload.error ?? "Request failed");
  return payload;
}

export function StrategyEnrollmentPanel({ enrollments }: { enrollments: StrategyEnrollmentView[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [credentialsOpen, setCredentialsOpen] = useState<string | null>(null);
  const [topUp, setTopUp] = useState<Record<string, string>>({});

  async function saveCredentials(event: React.FormEvent<HTMLFormElement>, enrollment: StrategyEnrollmentView) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(`credentials:${enrollment.id}`);
    try {
      await post(`/api/v1/marketplace/enrollments/${enrollment.id}/mt5-credentials`, {
        login: String(form.get("login") ?? ""),
        password: String(form.get("password") ?? ""),
        server: String(form.get("server") ?? ""),
        provider_name: String(form.get("provider") ?? "MetaTrader 5"),
        category: String(form.get("category") ?? "DEMO"),
        transport: "NATIVE_MT5",
      });
      setMessage(`${enrollment.strategy_name} MT5 credentials were stored securely.`);
      setCredentialsOpen(null);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save MT5 credentials");
    } finally {
      setBusy(null);
    }
  }

  async function topUpWallet(enrollment: StrategyEnrollmentView) {
    const amount = topUp[enrollment.id];
    if (!amount || Number(amount) <= 0) return;
    setBusy(`topup:${enrollment.id}`);
    try {
      const order = (await post(`/api/v1/marketplace/enrollments/${enrollment.id}/top-ups`, { amount_usd: amount }, crypto.randomUUID())) as unknown as CheckoutOrder;
      await loadRazorpay();
      if (!window.Razorpay) throw new Error("Razorpay Checkout is unavailable");
      new window.Razorpay({
        key: order.key_id,
        order_id: order.razorpay_order_id,
        amount: Math.round(Number(order.amount_usd) * 100),
        currency: order.currency,
        name: "ProtrixPlus",
        description: `${enrollment.strategy_name} escrow top-up`,
        handler: async (payment: { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string }) => {
          try {
            await post("/api/v1/payments/razorpay/verify", payment);
            setMessage("Top-up verified and applied to this strategy escrow wallet.");
            router.refresh();
          } catch (error) {
            setMessage(error instanceof Error ? error.message : "Top-up verification failed");
          }
        },
        theme: { color: "#36d6c6" },
      }).open();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create top-up checkout");
    } finally {
      setBusy(null);
    }
  }

  return <section className="enrollment-section">
    <div className="section-heading"><div><h2>Strategy accounts</h2></div><a href="/marketplace">Browse marketplace <Icon name="arrow" size={16} /></a></div>
    {message ? <p className="marketplace-message" role="status">{message}</p> : null}
    <div className="enrollment-grid">
      {enrollments.map((enrollment) => <article className="enrollment-card" key={enrollment.id}>
        <div className="strategy-card-topline"><strong>{enrollment.strategy_name}</strong><span className={enrollment.wallet.entry_allowed && enrollment.status === "ACTIVE" ? "status-good" : "status-warn"}>{enrollment.wallet.entry_allowed && enrollment.status === "ACTIVE" ? "ENTRY READY" : enrollment.status.replaceAll("_", " ")}</span></div>
        <div className="wallet-row"><div><span>Escrow wallet</span><strong>USD {Number(enrollment.wallet.balance).toFixed(2)}</strong></div><div><span>Required for entries</span><strong>USD {Number(enrollment.wallet.minimum).toFixed(2)}</strong></div></div>
        <p className="enrollment-copy">{enrollment.wallet.entry_allowed ? "New entries are eligible once the dedicated worker is connected." : "New entries are paused. Existing exits and risk-reducing actions remain allowed."}</p>
        <p className="enrollment-copy">MT5: {enrollment.account?.credential_configured ? `${enrollment.account.category} / ${enrollment.account.worker_status}` : "credentials required"}</p>
        <div className="enrollment-actions"><button className="secondary" aria-expanded={credentialsOpen === enrollment.id} aria-controls={`credentials-${enrollment.id}`} onClick={() => setCredentialsOpen(credentialsOpen === enrollment.id ? null : enrollment.id)}>{enrollment.account?.credential_configured ? "Update MT5" : "Set up MT5"}</button><label className="topup-field">Top-up (USD)<input aria-label={`${enrollment.strategy_name} top-up`} placeholder="Top-up USD" inputMode="decimal" value={topUp[enrollment.id] ?? ""} onChange={(event) => setTopUp({ ...topUp, [enrollment.id]: event.target.value })}/></label><button disabled={busy !== null} onClick={() => void topUpWallet(enrollment)}>{busy === `topup:${enrollment.id}` ? "…" : "Top up"}</button></div>
        {credentialsOpen === enrollment.id ? <form id={`credentials-${enrollment.id}`} className="credential-form" onSubmit={(event) => void saveCredentials(event, enrollment)}><label>Broker<input name="provider" defaultValue={enrollment.account?.provider_name ?? "MetaTrader 5"} required /></label><label>MT5 login<input name="login" autoComplete="username" required /></label><label>MT5 password<input name="password" type="password" autoComplete="current-password" required /></label><label>Server<input name="server" defaultValue={enrollment.account?.server_identifier ?? ""} required /></label><label>Account type<select name="category" defaultValue={enrollment.account?.category ?? "DEMO"}><option value="DEMO">Demo</option><option value="LIVE">Live</option></select></label><button disabled={busy !== null} type="submit">{busy === `credentials:${enrollment.id}` ? "Saving securely…" : "Save dedicated MT5 account"}</button><p>Credentials are sent to the vault and are never shown again.</p></form> : null}
      </article>)}
    </div>
    {!enrollments.length ? <div className="empty-state"><Icon name="layers" size={28} /><strong>Your first strategy starts here</strong><p>Choose a strategy from the marketplace, then connect its dedicated MT5 account.</p><a href="/marketplace">Explore available strategies &rarr;</a></div> : null}
  </section>;
}
