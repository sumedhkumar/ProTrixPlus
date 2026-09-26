import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppFooter } from "@/components/AppFooter";
import type { EngineStats } from "@/components/ExecutionEngineStatus";
import { SidebarNav, type TabDef } from "@/components/SidebarNav";
import { TopBar } from "@/components/TopBar";
import {
  apiFetch,
  type AdminMt5ConnectionView,
  type Identity,
  type OpsSummary,
  type StrategyView,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { canAccessAdmin } from "@/lib/roles";

const API_URL = process.env.PROTRIX_API_URL ?? "http://localhost:8000";

const TABS: TabDef[] = [
  { href: "/admin", label: "Strategy Lifecycle", icon: "▤" },
  { href: "/admin/alerts", label: "Alert Catalog", icon: "⚑" },
  { href: "/admin/clients", label: "Clients & Risk Caps", icon: "◎" },
  { href: "/admin/payments", label: "Payment Review", icon: "✉" },
  { href: "/admin/webhooks", label: "Webhook Telemetry", icon: "◔" },
  { href: "/admin/trades", label: "Global MT5 Trades", icon: "◷" },
  { href: "/admin/settlement", label: "EOD Profit-Share Settlement", icon: "$" },
];

async function checkApiHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const token = getToken();
  if (!token) redirect("/login");

  let identity: Identity;
  try {
    identity = await apiFetch<Identity>("/api/v1/me", token);
  } catch {
    redirect("/login");
  }
  if (!canAccessAdmin(identity.role)) redirect("/dashboard");

  const apiHealthy = await checkApiHealth();
  const strategies = await apiFetch<StrategyView[]>("/api/v1/admin/strategies", token).catch(
    () => [],
  );
  const opsSummary = await apiFetch<OpsSummary>("/api/v1/admin/ops-summary", token).catch(
    () => null,
  );
  const mt5Connections = await apiFetch<AdminMt5ConnectionView[]>(
    "/api/v1/admin/mt5-connections",
    token,
  ).catch(() => []);

  const engineStats: EngineStats = {
    apiHealthy,
    webhookPath: "/webhook/tradingview",
    idempotencyActive: true,
    bridgeLabel: "Connected MT5 Bridges",
    connectedBridges: mt5Connections.filter((c) => c.status === "CONNECTED").length,
    totalBridges: mt5Connections.length,
    totalSignals: opsSummary?.total_signals ?? null,
    signalsHiddenReason: "Signal ingestion telemetry unavailable",
  };

  return (
    <>
      <SidebarNav tabs={TABS} modeLabel="ADMINISTRATOR" />
      <div className="app-shell-with-sidebar">
        <TopBar identity={identity} strategies={strategies} engineStats={engineStats} />
        <div className="container">{children}</div>
        <AppFooter />
      </div>
    </>
  );
}
