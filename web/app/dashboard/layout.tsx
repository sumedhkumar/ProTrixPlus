import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppFooter } from "@/components/AppFooter";
import type { EngineStats } from "@/components/ExecutionEngineStatus";
import { SidebarNav, type TabDef } from "@/components/SidebarNav";
import { SubscriptionGraceBanner } from "@/components/SubscriptionStatus";
import { TopBar } from "@/components/TopBar";
import { apiFetch, type Identity, type Mt5ConnectionView, type StrategyView } from "@/lib/api";
import { getToken } from "@/lib/auth";

const API_URL = process.env.PROTRIX_API_URL ?? "http://localhost:8000";

const TABS: TabDef[] = [
  { href: "/dashboard/marketplace", label: "Strategy Marketplace", icon: "▤" },
  { href: "/dashboard", label: "My Trading Terminal", icon: "◧" },
  { href: "/dashboard/history", label: "Execution History", icon: "◷" },
  { href: "/dashboard/settlement", label: "EOD Settlement Ledger", icon: "$" },
  { href: "/dashboard/referrals", label: "Referrals & Rewards", icon: "◎" },
];

async function checkApiHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const token = getToken();
  if (!token) redirect("/login");

  let identity: Identity;
  try {
    identity = await apiFetch<Identity>("/api/v1/me", token);
  } catch {
    redirect("/login");
  }
  if (identity.must_change_password) redirect("/set-password");
  if (identity.subscription?.hard_blocked) redirect("/subscribe?renew=true");

  const apiHealthy = await checkApiHealth();
  const strategies = await apiFetch<StrategyView[]>("/api/v1/strategies", token).catch(() => []);
  const mt5Connection = await apiFetch<Mt5ConnectionView | null>(
    "/api/v1/me/mt5-connection",
    token,
  ).catch(() => null);

  const engineStats: EngineStats = {
    apiHealthy,
    webhookPath: "/webhook/tradingview",
    idempotencyActive: true,
    bridgeLabel: "Your MT5 Bridge",
    connectedBridges: mt5Connection?.status === "CONNECTED" ? 1 : 0,
    totalBridges: null,
    totalSignals: null,
    signalsHiddenReason: "System-wide signal volume is visible to admins only",
  };

  return (
    <>
      <SidebarNav tabs={TABS} modeLabel="CLIENT SUBSCRIBER" />
      <div className="app-shell-with-sidebar">
        <TopBar identity={identity} strategies={strategies} engineStats={engineStats} />
        <div className="container">
          {identity.subscription?.in_grace ? (
            <SubscriptionGraceBanner subscription={identity.subscription} />
          ) : null}
          {children}
        </div>
        <AppFooter />
      </div>
    </>
  );
}
