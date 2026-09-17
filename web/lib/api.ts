// Server-only module: only imported from Server Components and route handlers.
const API_URL = process.env.PROTRIX_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiFetch<T>(
  path: string,
  token: string | undefined,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, `${path} -> ${res.status} ${body.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export interface Identity {
  subject: string;
  role: "USER" | "SUPER_ADMIN";
  display_name: string;
  email: string;
  issued_at: string;
  expires_at: string;
}

export interface SignalView {
  id: string;
  signal_id: string;
  strategy_key: string;
  strategy_version: string;
  action: string;
  symbol: string;
  timeframe: string;
  payload_hash: string;
  event_time_utc: string;
  accepted_at: string;
  intent_count: number;
}

export interface ExecutionView {
  id: string;
  signal_ref: string;
  user_display_name: string;
  strategy_key: string;
  symbol: string;
  action: string;
  command_target: string;
  computed_lot: string;
  adapter: string;
  state: string;
  ticket_id: string | null;
  deal_id: string | null;
  reconcile_count: number;
  latency_dispatch_ms: number | null;
  latency_ack_ms: number | null;
  latency_fill_ms: number | null;
  entry_price: string | null;
  exit_price: string | null;
  realized_pnl: string | null;
  updated_at: string;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  assignment_count: number;
}

export interface AdminAssignment {
  id: string;
  user_display_name: string;
  strategy_key: string;
  strategy_version: string;
  master_lot: string;
  multiplier: string;
  multiplier_min: string;
  multiplier_max: string;
  status: string;
}

export interface StrategyView {
  id: string;
  strategy_key: string;
  strategy_version: string;
  name: string;
  description: string | null;
  symbol: string | null;
  timeframe: string | null;
  price: string | null;
  profit_share_percent: string | null;
  base_lot: string | null;
  is_active: boolean;
}

export interface MyAssignmentView {
  id: string;
  strategy_id: string;
  strategy_key: string;
  strategy_name: string;
  master_lot: string;
  multiplier: string;
  multiplier_min: string;
  multiplier_max: string;
  effective_lot: string;
  status: string;
  payment_status: string;
  purchased_at: string | null;
  expires_at: string | null;
}

export interface PnlSummary {
  realized_pnl: string;
  attributable_trades: number;
  realized_trades: number;
  match_rate_percent: number;
}

export interface Mt5ConnectionView {
  id: string;
  broker_server: string;
  login: string;
  status: string;
  last_checked_at: string | null;
  last_error: string | null;
}

export interface AdminMt5ConnectionView extends Mt5ConnectionView {
  user_id: string;
  user_display_name: string;
}

export interface OpsSummary {
  total_signals: number;
  total_executions: number;
  execution_state_counts: Record<string, number>;
  stuck_unknown_count: number;
  revoked_assignments: number;
}
