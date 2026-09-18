import type { PaymentInstructionsView } from "@/lib/api";

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        gap: 12,
        padding: "8px 0",
        borderBottom: "1px solid var(--panel-border)",
        fontSize: 13,
      }}
    >
      <span style={{ color: "var(--muted)" }}>{label}</span>
      {value ? (
        <code style={{ color: "var(--fg)" }}>{value}</code>
      ) : (
        <span style={{ color: "var(--dim)", fontStyle: "italic" }}>To be added by admin</span>
      )}
    </div>
  );
}

export function PaymentInstructions({
  instructions,
}: {
  instructions: PaymentInstructionsView | null;
}) {
  const i = instructions;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <span className="card-title">Transfer Payment</span>
        <span className="badge-pill badge-neutral">Manual - no gateway yet</span>
      </div>

      <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
        <div
          style={{
            width: 132,
            height: 132,
            flex: "none",
            borderRadius: 10,
            border: "1px dashed var(--card-border)",
            background: "rgba(255,255,255,0.02)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
          }}
        >
          {i?.qr_code_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={i.qr_code_url}
              alt="UPI payment QR code"
              style={{ width: "100%", height: "100%", objectFit: "contain" }}
            />
          ) : (
            <div style={{ textAlign: "center", color: "var(--dim)", padding: 8 }}>
              <div style={{ fontSize: 28, lineHeight: 1 }}>▦</div>
              <div style={{ fontSize: 10.5, marginTop: 6 }}>QR code coming soon</div>
            </div>
          )}
        </div>

        <div style={{ flex: 1, minWidth: 200 }}>
          <Row label="UPI ID" value={i?.upi_id ?? null} />
          <Row label="Account name" value={i?.bank_account_name ?? null} />
          <Row label="Account number" value={i?.bank_account_number ?? null} />
          <Row label="IFSC" value={i?.bank_ifsc ?? null} />
          <Row label="Bank" value={i?.bank_name ?? null} />
        </div>
      </div>

      <p style={{ fontSize: 12, color: "var(--dim)", marginTop: 14, marginBottom: 0 }}>
        Scan the QR or transfer to the account above, then submit your transaction / UTR
        reference in the form.
      </p>
    </div>
  );
}
