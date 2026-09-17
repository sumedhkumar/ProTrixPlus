import { NextResponse } from "next/server";

import { getToken } from "@/lib/auth";

const API_URL = process.env.PROTRIX_API_URL ?? "http://localhost:8000";
const WEBHOOK_SECRET = process.env.PROTRIX_WEBHOOK_SHARED_SECRET ?? "";

interface SimulateBody {
  strategy_key?: unknown;
  strategy_version?: unknown;
  symbol?: unknown;
  timeframe?: unknown;
  action?: unknown;
  signal_id?: unknown;
  tamper_secret?: unknown;
  // For a true duplicate test: idempotency is keyed on the *whole* payload
  // hash, not just signal_id, so re-dispatching must reuse the exact same
  // event_time_utc as the original or the api correctly treats it as a
  // conflict (a reused id with different content), not a duplicate.
  event_time_utc?: unknown;
}

function randomId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
}

/** POST /api/simulate-signal -> real webhook ingestion (not fake). The real
 * webhook secret is read from the server env and never sent to the browser;
 * `tamper_secret: true` deliberately substitutes a wrong one, to let the
 * simulator UI demonstrate a real 401 without ever exposing the real value. */
export async function POST(req: Request) {
  const token = getToken();
  if (!token) {
    return NextResponse.json({ error: "not signed in" }, { status: 401 });
  }

  const body = (await req.json().catch(() => ({}))) as SimulateBody;
  const action = typeof body.action === "string" ? body.action : "BUY";
  const strategyKey = typeof body.strategy_key === "string" ? body.strategy_key : null;
  const strategyVersion = typeof body.strategy_version === "string" ? body.strategy_version : "1.0";
  const symbol = typeof body.symbol === "string" ? body.symbol : "EURUSD";
  const timeframe = typeof body.timeframe === "string" ? body.timeframe : "15m";
  const signalId = typeof body.signal_id === "string" && body.signal_id ? body.signal_id : `web-sim-${randomId()}`;
  const eventTimeUtc = typeof body.event_time_utc === "string" ? body.event_time_utc : new Date().toISOString();
  const tamper = body.tamper_secret === true;

  if (!strategyKey) {
    return NextResponse.json({ error: "strategy_key is required" }, { status: 400 });
  }

  const envelope = {
    schema_version: "1.0",
    strategy_key: strategyKey,
    strategy_version: strategyVersion,
    signal_id: signalId,
    event_time_utc: eventTimeUtc,
    action,
    symbol,
    timeframe,
  };

  const res = await fetch(`${API_URL}/webhook/tradingview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Webhook-Token": tamper ? `${WEBHOOK_SECRET}-tampered` : WEBHOOK_SECRET,
    },
    body: JSON.stringify(envelope),
    cache: "no-store",
  });
  const apiResult = await res.json().catch(() => ({}));
  return NextResponse.json(
    { ...apiResult, sent_envelope: envelope },
    { status: res.status },
  );
}
