// Server-only module: only imported from Server Components and route handlers.
import type { Role } from "@/lib/roles";

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

export interface SubscriptionStatusView {
  package: string | null;
  start: string | null;
  end: string | null;
  days_remaining: number | null;
  is_expired: boolean;
  in_grace: boolean;
  grace_ends_at: string | null;
  hard_blocked: boolean;
}

export interface Identity {
  subject: string;
  role: Role;
  extra_roles: Role[];
  display_name: string;
  email: string;
  issued_at: string;
  expires_at: string;
  must_change_password: boolean;
  phone: string | null;
  subscription: SubscriptionStatusView | null;
}

export interface PaymentInstructionsView {
  bank_account_name: string | null;
  bank_account_number: string | null;
  bank_ifsc: string | null;
  bank_name: string | null;
  upi_id: string | null;
  qr_code_url: string | null;
}

export interface PaymentSubmissionView {
  id: string;
  user_id: string | null;
  name: string;
  email: string;
  phone: string;
  package: string;
  utr_reference: string;
  status: string;
  submitted_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  rejection_reason: string | null;
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
  last_error: string | null;
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
  extra_roles: string[];
  is_active: boolean;
  /** False until an admin-invited account completes its first password setup. */
  has_password: boolean;
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
  win_rate: string | null;
  max_drawdown: string | null;
  description_short: string | null;
  is_active: boolean;
  min_balance: string | null;
}

// "SETUP_INCOMPLETE" = admin has granted access but the client hasn't yet
// completed the setup wizard (sizing + MT5 connection + risk confirmation).
export type AssignmentStatus = "SETUP_INCOMPLETE" | "ACTIVE" | "PAUSED";

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
  status: AssignmentStatus;
  payment_status: string;
  purchased_at: string | null;
  expires_at: string | null;
  confirmed_risk_disclosure: boolean;
  activated_at: string | null;
}

export interface AlertView {
  id: string;
  strategy_id: string | null;
  name: string;
  symbol: string;
  lot_size: string;
  timeframe: string;
  created_at: string;
  updated_at: string;
}

export interface AlertChangelogEntry {
  event_type: string;
  actor: string | null;
  data: Record<string, string | null | string[]>;
  created_at: string;
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
  metaapi_account_id: string | null;
  metaapi_region: string | null;
}

export interface LiveBalance {
  available: boolean;
  reason?: string;
  balance?: number;
  equity?: number;
  free_margin?: number;
  currency?: string;
  leverage?: number;
  trade_mode?: string;
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
  duplicate_signal_count: number;
  mt5_disconnected_count: number;
  broker_rejected_count: number;
}
