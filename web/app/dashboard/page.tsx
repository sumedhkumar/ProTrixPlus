import { redirect } from "next/navigation";

import { ExecutionsTable } from "@/components/ExecutionsTable";
import { IdentityBar } from "@/components/IdentityBar";
import { SignalsTable } from "@/components/SignalsTable";
import { apiFetch, type ExecutionView, type Identity, type SignalView } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const token = getToken();
  if (!token) redirect("/login");

  let identity: Identity;
  try {
    identity = await apiFetch<Identity>("/api/v1/me", token);
  } catch {
    redirect("/login");
  }

  const [signals, executions] = await Promise.all([
    apiFetch<SignalView[]>("/api/v1/signals", token),
    apiFetch<ExecutionView[]>("/api/v1/executions", token),
  ]);

  return (
    <>
      <IdentityBar identity={identity} />
      <div className="container">
        <h1>User dashboard</h1>
        <p style={{ color: "var(--muted)" }}>
          Signals and your executions, read from the api. Stored data only.
        </p>
        <SignalsTable signals={signals} />
        <ExecutionsTable executions={executions} />
      </div>
    </>
  );
}
