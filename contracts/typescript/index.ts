/**
 * Shared Protrixplus contract types (schema v1.0, FROZEN).
 *
 * Money / price / lot / fraction values are strings on the wire and in these
 * types - never `number` - so binary-float precision loss cannot occur.
 * `master_lot_info` is informational only; the stored backend strategy
 * configuration is always authoritative.
 */

export const SCHEMA_VERSION = "1.0" as const;

export type WebhookAction =
  | "BUY"
  | "SELL"
  | "CLOSE"
  | "PARTIAL_CLOSE"
  | "MODIFY_SLTP"
  | "EMERGENCY_CLOSE";

export type CommandTarget = "ENTRY" | "CLOSE" | "MODIFY" | "EMERGENCY";

export interface MasterLotInfo {
  master_lot?: string | null;
  note?: string | null;
  [k: string]: unknown;
}

export interface WebhookEnvelope {
  schema_version: typeof SCHEMA_VERSION;
  strategy_key: string;
  strategy_version: string;
  signal_id: string;
  event_time_utc: string;
  action: WebhookAction;
  symbol: string;
  timeframe: string;
  position_ref?: string | null;
  close_fraction?: string | null;
  stop_loss?: string | null;
  take_profit?: string | null;
  master_lot_info?: MasterLotInfo | null;
}

export type Role = "USER" | "SUPER_ADMIN";

export type ExecutionState =
  | "RECEIVED"
  | "INTENT_CREATED"
  | "QUEUED"
  | "DISPATCHED"
  | "ACKNOWLEDGED"
  | "FILLED"
  | "REJECTED"
  | "UNKNOWN"
  | "RECONCILED";

/** Read model returned by GET /api/v1/me */
export interface Identity {
  subject: string;
  role: Role;
  display_name: string;
  email: string;
  issued_at: string;
  expires_at: string;
}

/** Read model returned by GET /api/v1/signals */
export interface SignalView {
  id: string;
  signal_id: string;
  strategy_key: string;
  strategy_version: string;
  action: WebhookAction;
  symbol: string;
  timeframe: string;
  payload_hash: string;
  event_time_utc: string;
  accepted_at: string;
  intent_count: number;
}

/** Read model returned by GET /api/v1/executions */
export interface ExecutionView {
  id: string;
  signal_id: string;
  signal_ref: string;
  user_id: string;
  user_display_name: string;
  strategy_key: string;
  symbol: string;
  command_target: CommandTarget;
  computed_lot: string;
  adapter: string;
  state: ExecutionState;
  ticket_id: string | null;
  deal_id: string | null;
  reconcile_count: number;
  latency_dispatch_ms: number | null;
  latency_ack_ms: number | null;
  latency_fill_ms: number | null;
  updated_at: string;
}

export const ACTION_TO_COMMAND_TARGET: Record<WebhookAction, CommandTarget> = {
  BUY: "ENTRY",
  SELL: "ENTRY",
  CLOSE: "CLOSE",
  PARTIAL_CLOSE: "CLOSE",
  MODIFY_SLTP: "MODIFY",
  EMERGENCY_CLOSE: "EMERGENCY",
};
