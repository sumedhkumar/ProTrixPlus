import { ExecutionHistoryTable } from "@/components/ExecutionHistoryTable";
import { apiFetch, type ExecutionView } from "@/lib/api";
import { getToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const token = getToken()!;
  const executions = await apiFetch<ExecutionView[]>("/api/v1/executions", token);

  return (
    <>
      <h1>My Trading &amp; Execution Records</h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Every trade is attributed to a signal, strategy configuration, and execution ticket.
      </p>
      <ExecutionHistoryTable executions={executions} title="Execution history" showClientColumn={false} />
    </>
  );
}
