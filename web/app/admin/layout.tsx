import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppFooter } from "@/components/AppFooter";
import type { EngineStats } from "@/components/ExecutionEngineStatus";
import { TabNav, type TabDef } from "@/components/TabNav";
import { TopBar } from "@/components/TopBar";
import {
  apiFetch,
  type AdminMt5ConnectionView,
  type Identity,
  type OpsSummary,
  type StrategyView,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { canAccessAdmin, canRead, type Capability, type Role } from "@/lib/roles";

const API_URL = process.env.PROTRIX_API_URL ?? "http://localhost:8000";

const TABS: (TabDef & { capabilities: Capability[]; superOnly?: boolean })[] = [
  { href: "/admin", label: "Strategy Lifecycle", icon: "▤", capabilities: ["strategy"] },
  { href: "/admin/alerts", label: "Alert Catalog", icon: "⚑", capabilities: ["strategy"] },
  // Clients mixes ops data (user/MT5 status) with a finance action (entitlement
  // grants), so either capability is enough to see the tab.
  {
    href: "/admin/clients",
    label: "Clients & Risk Caps",
    icon: "◎",
    capabilities: ["ops", "finance"],
  },
  { href: "/admin/payments", label: "Payment Review", icon: "✉", capabilities: ["finance"] },
  { href: "/admin/webhooks", label: "Webhook Telemetry", icon: "◔", capabilities: ["ops"] },
  { href: "/admin/trades", label: "Global MT5 Trades", icon: "◷", capabilities: ["ops"] },
  {
    href: "/admin/settlement",
    label: "EOD Profit-Share Settlement",
    icon: "$",
    capabilities: ["finance"],
  },
  // Managing who else is an admin isn't a shared ops/strategy/finance
  // capability - only SUPER_ADMIN gets this tab.
  { href: "/admin/team", label: "Admin Team", icon: "★", capabilities: [], superOnly: true },
];

function tabsForRole(role: Role, extraRoles: readonly Role[]): TabDef[] {
  return TABS.filter((tab) =>
    tab.superOnly
      ? role === "SUPER_ADMIN"
      : tab.capabilities.some((cap) => canRead(role, cap, extraRoles)),
  );
}

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
      <TopBar identity={identity} strategies={strategies} engineStats={engineStats} />
      <TabNav tabs={tabsForRole(identity.role, identity.extra_roles)} modeLabel="ADMINISTRATOR" />
      <div className="container">{children}</div>
      <AppFooter />
    </>
  );
}
