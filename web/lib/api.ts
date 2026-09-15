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
  command_target: string;
  computed_lot: string;
  adapter: string;
  state: string;
  ticket_id: string | null;
  deal_id: string | null;
  last_error: string | null;
  reconcile_count: number;
  latency_dispatch_ms: number | null;
  latency_ack_ms: number | null;
  latency_fill_ms: number | null;
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

export interface PortfolioAssignment {
  id: string;
  strategy_key: string;
  strategy_version: string;
  master_lot: string;
  multiplier: string;
  multiplier_min: string;
  multiplier_max: string;
  status: string;
}

export interface Portfolio {
  user: { id: string; display_name: string; email: string };
  wallet: { currency: string; balance: string };
  account: {
    provider_name: string;
    server_identifier: string | null;
    category: string;
    transport: string;
    status: string;
    external_account_ref: string | null;
    credential_key_ref: string | null;
    worker_adapter: string | null;
    worker_name: string | null;
    worker_heartbeat_at: string | null;
    worker_status: "HEALTHY" | "STALE" | "NO_WORKER";
  } | null;
  subscription: {
    plan_code: string;
    status: string;
    starts_at: string;
    ends_at: string;
  } | null;
  controls: {
    admin_suspended: boolean;
    risk_blocked: boolean;
    kill_switch: boolean;
  } | null;
  risk_profile: {
    max_lot: string;
    max_open_trades: number;
    max_daily_loss: string;
    allowed_symbols: string[];
  } | null;
  assignments: PortfolioAssignment[];
  managed_positions: Array<{
    id: string;
    source_position_ref: string;
    broker_position_ref: string;
    symbol: string;
    side: string;
    initial_volume: string;
    remaining_volume: string;
    status: string;
    updated_at: string;
  }>;
}

export interface AdminOperation {
  user_id: string;
  email: string;
  display_name: string;
  wallet_balance: string;
  account: {
    provider_name: string;
    server_identifier: string | null;
    category: string;
    transport: string;
    status: string;
    external_account_ref: string | null;
    credential_key_ref: string | null;
    worker_adapter: string | null;
    worker_name: string | null;
    worker_heartbeat_at: string | null;
    worker_status: "HEALTHY" | "STALE" | "NO_WORKER";
  } | null;
  subscription_status: string | null;
  subscription: {
    plan_code: string;
    status: "ACTIVE" | "EXPIRED" | "DISABLED";
    starts_at: string;
    ends_at: string;
  } | null;
  controls: { admin_suspended: boolean; risk_blocked: boolean; kill_switch: boolean } | null;
  risk: {
    max_lot: string;
    max_open_trades: number;
    max_daily_loss: string;
    allowed_symbols: string[];
  } | null;
}
