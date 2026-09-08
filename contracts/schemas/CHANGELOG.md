# Webhook envelope schema changelog

## 1.0 — FROZEN (S0)

Initial frozen wire contract: `webhook_envelope.v1.json`.

Fields: `schema_version`, `strategy_key`, `strategy_version`, `signal_id`,
`event_time_utc`, `action`, `symbol`, `timeframe`, `position_ref`,
`close_fraction`, `stop_loss`, `take_profit`, `master_lot_info`.

Rules baked into the schema:

- `schema_version` is `const: "1.0"`.
- `position_ref` is required for `CLOSE`, `PARTIAL_CLOSE`, `MODIFY_SLTP`,
  `EMERGENCY_CLOSE`.
- `close_fraction` is required for `PARTIAL_CLOSE`.
- All money / price / lot / fraction values are JSON **strings**, never JSON
  numbers, so producers cannot introduce binary-float precision loss on the wire.
- `master_lot_info` is informational only. The stored
  `strategy_assignments.master_lot` is always authoritative for sizing.

Any change to the shape is a new file (`webhook_envelope.v2.json`) plus a new
`schema_version` value. v1.0 is never edited.
