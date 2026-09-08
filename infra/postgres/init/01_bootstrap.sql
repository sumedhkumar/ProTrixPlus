-- Runs once on an empty data directory (docker-entrypoint-initdb.d).
-- Schema itself is owned by Alembic (api service). This only sets DB-wide
-- defaults; the audit_events insert-only trigger is installed by migration 0001.

ALTER DATABASE protrix SET timezone TO 'UTC';

-- Fail loudly if someone later tries to store naive local timestamps.
ALTER DATABASE protrix SET datestyle TO 'ISO, YMD';
