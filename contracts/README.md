# /contracts

Things `api`, `worker`, and `web` must agree on at all times.

| Path | What |
| --- | --- |
| `schemas/webhook_envelope.v1.json` | **FROZEN** wire contract, schema v1.0. Language-agnostic JSON Schema (draft-07). |
| `schemas/CHANGELOG.md` | Rules baked into v1.0; how a v2 would be introduced. |
| `python/protrix_contracts/` | Pip-installable package: envelope validation, canonical hashing, execution lifecycle, Decimal money helpers, **and** the shared SQLAlchemy models (the DB is a contract too). |
| `typescript/index.ts` | Hand-written TS types for the envelope + dashboard read models. |

## Freeze rules

- `schema_version` is `const "1.0"`. v1.0 JSON is never edited in place.
- The stored backend strategy configuration is always authoritative. Wire values
  such as `master_lot_info` are informational only and never used for sizing or
  risk.
- Money / price / lot / fraction fields are strings, never JSON numbers.
- `python/protrix_contracts/schemas/webhook_envelope.v1.json` is a build-time
  copy of the canonical file in `schemas/`. `test_envelope.py` fails if the two
  ever drift.

## Local dev

```bash
cd contracts/python
python -m pip install -e ".[dev]"
pytest -q
ruff check .
mypy protrix_contracts
```

```bash
cd contracts/typescript
npm ci
npm run typecheck
```
