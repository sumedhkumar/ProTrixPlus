import { ExecutionHistoryTable } from "@/components/ExecutionHistoryTable";
import { apiFetch, type ExecutionView } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function GlobalTradesPage() {
  const token = getToken()!;
  const executions = await apiFetch<ExecutionView[]>("/api/v1/executions", token);

  return (
    <>
      <h1>Global MT5 Execution &amp; Audit History</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Every trade across every client, attributed to a signal, strategy, and execution ticket.
      </p>
      <ExecutionHistoryTable executions={executions} title="All executions" showClientColumn={true} />
    </>
  );
}
