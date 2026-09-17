"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AdminMarketplaceEnrollment, AdminUser, MarketplaceOffer } from "@/lib/api";

async function adminMutate(method: string, path: string, body: object) {
  const response = await fetch("/api/admin-control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ method, path, body }) });
  const payload = (await response.json().catch(() => ({}))) as { error?: string };
  if (!response.ok) throw new Error(payload.error ?? "Admin operation failed");
}

export function MarketplaceAdminControls({ users, offers, enrollments }: { users: AdminUser[]; offers: MarketplaceOffer[]; enrollments: AdminMarketplaceEnrollment[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function run(key: string, callback: () => Promise<void>) {
    setBusy(key); setMessage(null);
    try { await callback(); setMessage("Marketplace operation saved."); router.refresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Marketplace operation failed"); }
    finally { setBusy(null); }
  }

  return <section className="panel marketplace-admin">
    <h2>Marketplace controls</h2>
    <p style={{ color: "var(--muted)" }}>Manual activation credits configured escrow; all wallet corrections remain append-only.</p>
    {message ? <p className="marketplace-message" role="status">{message}</p> : null}
    <div className="control-grid">
      <form className="control-card" onSubmit={(event) => { event.preventDefault(); const values = new FormData(event.currentTarget); void run("activate", () => adminMutate("POST", "/api/v1/admin/marketplace/manual-activations", { user_id: String(values.get("user_id")), strategy_id: String(values.get("strategy_id")), idempotency_key: crypto.randomUUID(), reason: String(values.get("reason") ?? "Manual activation") })); }}>
        <h3>Manual activation</h3><label>User<select name="user_id">{users.filter((user) => user.role === "USER").map((user) => <option key={user.id} value={user.id}>{user.display_name} · {user.email}</option>)}</select></label><label>Strategy<select name="strategy_id">{offers.map((offer) => <option key={offer.strategy_id} value={offer.strategy_id}>{offer.name} · USD {offer.price_usd}</option>)}</select></label><label>Reason<input name="reason" defaultValue="Manual activation" /></label><button disabled={busy !== null} type="submit">Activate + credit escrow</button>
      </form>
      {offers.map((offer) => <form className="control-card" key={offer.strategy_id} onSubmit={(event) => { event.preventDefault(); const values = new FormData(event.currentTarget); void run(`offer:${offer.strategy_id}`, () => adminMutate("PUT", `/api/v1/admin/marketplace/strategies/${offer.strategy_id}/offer`, { description: String(values.get("description")), price_usd: String(values.get("price")), platform_fee_usd: String(values.get("fee")), escrow_credit_usd: String(values.get("credit")), duration_days: Number(values.get("duration")), minimum_wallet_usd: String(values.get("minimum")), profit_share_rate: String(values.get("share")), is_published: values.get("published") === "on" })); }}>
        <h3>{offer.name}</h3><label>Description<input name="description" defaultValue={offer.description} /></label><div className="control-row"><label>Price<input name="price" defaultValue={offer.price_usd} /></label><label>Fee<input name="fee" defaultValue={offer.platform_fee_usd} /></label><label>Escrow<input name="credit" defaultValue={offer.escrow_credit_usd} /></label></div><div className="control-row"><label>Days<input name="duration" defaultValue={offer.duration_days} /></label><label>Minimum<input name="minimum" defaultValue={offer.minimum_wallet_usd} /></label><label>Share<input name="share" defaultValue={offer.profit_share_rate} /></label></div><label><input name="published" type="checkbox" defaultChecked={offer.is_published} /> Published</label><button disabled={busy !== null} type="submit">Save offer</button>
      </form>)}
    </div>
    <div className="control-grid" style={{ marginTop: 12 }}>
      {enrollments.map((enrollment) => <form className="control-card" key={enrollment.id} onSubmit={(event) => { event.preventDefault(); const values = new FormData(event.currentTarget); const amount = String(values.get("amount")); if (!amount || Number(amount) === 0) return; void run(`wallet:${enrollment.id}`, () => adminMutate("POST", `/api/v1/admin/marketplace/enrollments/${enrollment.id}/wallet-adjustments`, { amount_usd: amount, idempotency_key: crypto.randomUUID(), reason: String(values.get("reason") ?? "Admin adjustment") })); }}>
        <h3>{enrollment.user_display_name} · {enrollment.strategy_name}</h3><p>Escrow: <strong>USD {enrollment.wallet.balance}</strong> · floor USD {enrollment.wallet.minimum}</p><label>Adjustment<input name="amount" placeholder="e.g. 10.00 or -5.00" inputMode="decimal" /></label><label>Reason<input name="reason" defaultValue="Admin adjustment" /></label><button disabled={busy !== null} type="submit">Adjust wallet</button>
      </form>)}
    </div>
  </section>;
}
