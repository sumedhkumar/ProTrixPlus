"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { AdminMt5ConnectionView } from "@/lib/api";

export function MetaApiAttachCell({ connection }: { connection: AdminMt5ConnectionView | undefined }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [accountId, setAccountId] = useState(connection?.metaapi_account_id ?? "");
  const [region, setRegion] = useState(connection?.metaapi_region ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!connection) {
    return <span style={{ color: "var(--dim)", fontSize: 12 }}>no MT5 bridge yet</span>;
  }

  if (!editing) {
    return connection.metaapi_account_id ? (
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="badge-pill badge-green" title={connection.metaapi_account_id}>
          {connection.metaapi_region}
        </span>
        <button className="secondary" style={{ padding: "2px 8px" }} onClick={() => setEditing(true)}>
          Edit
        </button>
      </div>
    ) : (
      <button className="secondary" style={{ padding: "2px 8px" }} onClick={() => setEditing(true)}>
        Attach MetaApi account
      </button>
    );
  }

  async function save() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/admin/mt5-connections/${connection!.id}/metaapi`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metaapi_account_id: accountId, metaapi_region: region }),
    });
    setBusy(false);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `failed (${res.status})`);
      return;
    }
    setEditing(false);
    router.refresh();
  }

  return (
    <div style={{ display: "grid", gap: 4, minWidth: 200 }}>
      <input
        placeholder="MetaApi account id (UUID)"
        value={accountId}
        onChange={(e) => setAccountId(e.target.value)}
        style={{ fontSize: 12, padding: "4px 6px" }}
      />
      <input
        placeholder="region, e.g. london"
        value={region}
        onChange={(e) => setRegion(e.target.value)}
        style={{ fontSize: 12, padding: "4px 6px" }}
      />
      <div style={{ display: "flex", gap: 6 }}>
        <button
          className="secondary"
          style={{ padding: "2px 8px", fontSize: 12 }}
          disabled={busy}
          onClick={() => void save()}
        >
          Save
        </button>
        <button
          className="secondary"
          style={{ padding: "2px 8px", fontSize: 12 }}
          onClick={() => setEditing(false)}
        >
          Cancel
        </button>
      </div>
      {error ? <span style={{ color: "var(--bad)", fontSize: 11 }}>{error}</span> : null}
    </div>
  );
}
