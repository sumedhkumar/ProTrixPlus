# ADR-001: MetaApi.cloud as the MT5 execution transport (later phase)

- **Status:** Accepted (records a future direction; not implemented in S0)
- **Date:** 2026-09-08
- **Deciders:** Protrixplus core
- **Supersedes:** the previously assumed self-hosted Windows MT5 execution service

## Context

Protrixplus must place and manage MT5 orders on many client broker accounts. The
earlier assumption was a self-hosted Windows service running MT5 terminals. That
is operationally heavy (Windows hosts, terminal lifecycle, RDP, patching) and
hard to scale or run in CI.

S0 (this milestone) ships **no** execution transport at all - only a
`MockExecutionAdapter` behind an `ExecutionAdapter` interface.

## Decision

In a later phase, the MT5 execution transport will be **MetaApi.cloud**, reached
through a `MetaApiExecutionAdapter` that implements the exact same
`ExecutionAdapter` interface as the mock:

```
place(order_intent)      -> { ticket_id, deal_id, status }
sync_positions(account)  -> [ position/deal ... ]     # for reconciliation
```

Constraints that this ADR fixes:

1. **MetaApi is transport only.** All eligibility, position sizing, multiplier
   bounds, and risk logic stay inside Protrixplus (`worker/app/eligibility.py`,
   `worker/app/sizing.py`, the order-intent model). The adapter converts an
   already-decided intent into a broker call and reports back. It never decides
   *whether* or *how big*.
2. **CopyFactory is not used.** No MetaApi copy-trading. Fan-out and per-user
   sizing are ours.
3. **MetaApi Risk Management API is not used.** Drawdown / kill-switch logic is
   ours.
4. **The credential vault stays system-of-record.** `CredentialVault`
   (`api/app/vault/`) holds broker credentials and issues **short-lived, scoped,
   rotating** handles just-in-time. The real adapter receives a
   `ScopedCredentialHandle` and materialises the token only for the duration of a
   single call (`handle.use()`), never logging or returning it. MetaApi is never
   given a long-lived static secret from us.
5. **UNKNOWN is not FAILED.** A transport timeout sets the execution to `UNKNOWN`
   and triggers `sync_positions`-based reconciliation. The adapter must never
   auto-resend an order.

## Consequences

- No Windows execution hosts to run; the transport becomes an HTTP integration.
- The mock adapter's request/response shapes already mirror MetaApi (broker
  ticket ids, deal ids, a position/deal sync list) so swapping implementations is
  contained.
- New external dependency (MetaApi.cloud) and its credentials - handled through
  the vault, added to the dependency/security review at that step.
- CI keeps using the mock; a contract test against MetaApi's sandbox is added in
  the step that introduces the real adapter.

## Affected future steps

| Step | Work |
| --- | --- |
| 05 | Introduce `MetaApiExecutionAdapter` implementing `ExecutionAdapter`; wire adapter selection by config; sandbox contract test. |
| 06 | Real `CredentialVault` backend (rotating, scoped, short-TTL); remove fake vault; secret-scan gates. |
| 07 | Reconciliation worker hardening: periodic `sync_positions`, UNKNOWN sweeps, idempotent resolution against real deal ids. |
| 08 | Per-account MetaApi provisioning / teardown; region pinning; rate-limit handling and backoff. |
| 09 | Settlement schedule display in IST; latency-segment SLOs on the real transport. |
