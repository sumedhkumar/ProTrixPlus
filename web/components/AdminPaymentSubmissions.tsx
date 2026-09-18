"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { PaymentSubmissionView } from "@/lib/api";

const PACKAGE_LABEL: Record<string, string> = {
  PLAN_3M: "3-Month",
  PLAN_6M: "6-Month",
  PLAN_12M: "1-Year",
};

const STATUS_BADGE: Record<string, string> = {
  PENDING: "badge-warn",
  APPROVED: "badge-green",
  REJECTED: "badge-bad",
};

export function AdminPaymentSubmissions({
  submissions,
}: {
  submissions: PaymentSubmissionView[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  async function approve(id: string) {
    setBusy(id);
    setError(null);
    const res = await fetch(`/api/admin/payment-submissions/${id}/approve`, { method: "POST" });
    setBusy(null);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `approve failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  async function reject(id: string) {
    setBusy(id);
    setError(null);
    const res = await fetch(`/api/admin/payment-submissions/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason || null }),
    });
    setBusy(null);
    setRejecting(null);
    setReason("");
    if (!res.ok) {
      setError(`reject failed (${res.status})`);
      return;
    }
    router.refresh();
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Payment submissions</span>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table data-testid="admin-payment-submissions">
          <thead>
            <tr>
              <th>name</th>
              <th>contact</th>
              <th>package</th>
              <th>UTR reference</th>
              <th>account</th>
              <th>status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {submissions.map((s) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>
                  {s.email}
                  <br />
                  <span style={{ color: "var(--dim)", fontSize: 11 }}>{s.phone}</span>
                </td>
                <td>{PACKAGE_LABEL[s.package] ?? s.package}</td>
                <td>
                  <code>{s.utr_reference}</code>
                </td>
                <td>
                  {s.user_id ? (
                    <span className="badge-pill badge-blue">existing account</span>
                  ) : (
                    <span className="badge-pill badge-neutral">new applicant</span>
                  )}
                </td>
                <td>
                  <span className={`badge-pill ${STATUS_BADGE[s.status] ?? "badge-neutral"}`}>
                    {s.status}
                  </span>
                </td>
                <td>
                  {s.status === "PENDING" ? (
                    rejecting === s.id ? (
                      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <input
                          placeholder="reason (optional)"
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          style={{ fontSize: 12, padding: "4px 8px" }}
                        />
                        <button
                          className="btn-danger"
                          disabled={busy === s.id}
                          onClick={() => void reject(s.id)}
                        >
                          Confirm
                        </button>
                        <button className="secondary" onClick={() => setRejecting(null)}>
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button
                          className="btn-primary"
                          disabled={busy === s.id}
                          onClick={() => void approve(s.id)}
                        >
                          Approve
                        </button>
                        <button
                          className="secondary"
                          disabled={busy === s.id}
                          onClick={() => setRejecting(s.id)}
                        >
                          Reject
                        </button>
                      </div>
                    )
                  ) : (
                    <span style={{ color: "var(--dim)", fontSize: 12 }}>
                      {s.reviewed_at ? new Date(s.reviewed_at).toLocaleDateString() : ""}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {submissions.length === 0 ? <p className="empty">No payment submissions yet.</p> : null}
      </div>

      {error ? (
        <p style={{ color: "var(--bad)", marginTop: 12 }} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
