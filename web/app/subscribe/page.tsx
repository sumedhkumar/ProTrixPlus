import { PaymentInstructions } from "@/components/PaymentInstructions";
import { SubscribeForm } from "@/components/SubscribeForm";
import { apiFetch, type Identity, type PaymentInstructionsView } from "@/lib/api";
import { getToken } from "@/lib/auth";

const PACKAGE_KEYS = ["PLAN_3M", "PLAN_6M", "PLAN_12M"];

const STEPS = [
  ["1", "Transfer payment", "Use the UPI QR code or bank details shown above."],
  ["2", "Submit your reference", "Paste the transaction / UTR reference into the form."],
  ["3", "We confirm by email", "Our team reviews it, usually within one business day."],
  ["4", "You're all set", "Existing accounts get extended access; new applicants get login details."],
];

export default async function SubscribePage({
  searchParams,
}: {
  searchParams: { package?: string; renew?: string };
}) {
  const token = getToken();
  let identity: Identity | null = null;
  if (token) {
    identity = await apiFetch<Identity>("/api/v1/me", token).catch(() => null);
  }
  const instructions = await apiFetch<PaymentInstructionsView>(
    "/api/v1/payments/instructions",
    undefined,
  ).catch(() => null);

  const initialPackage = PACKAGE_KEYS.includes(searchParams.package ?? "")
    ? (searchParams.package as string)
    : "PLAN_3M";

  return (
    <div className="login-split">
      <div>
        <span className="badge-pill badge-teal">💳 Payment Confirmation</span>
        <h1 style={{ fontSize: 34, lineHeight: 1.15, margin: "16px 0" }}>
          {searchParams.renew ? "Renew your subscription" : "Activate a paid plan"}
        </h1>
        <p style={{ color: "var(--muted)", fontSize: 15, marginBottom: 20, maxWidth: 440 }}>
          There&apos;s no payment gateway yet - transfer payment to ProTrixPlus, then submit your
          transaction / UTR reference below.
        </p>
        {identity?.subscription?.hard_blocked ? (
          <div className="card" style={{ borderColor: "rgba(240,87,107,0.35)", marginBottom: 20 }}>
            <p style={{ fontSize: 13, color: "var(--bad)", margin: 0 }}>
              Your subscription has expired. Submit a renewal below to restore dashboard access.
            </p>
          </div>
        ) : null}

        <PaymentInstructions instructions={instructions} />

        <div className="card" style={{ padding: 24 }}>
          <div className="card-head">
            <span className="card-title">What happens next</span>
          </div>
          <div style={{ display: "grid", gap: 18 }}>
            {STEPS.map(([n, title, desc]) => (
              <div key={n} style={{ display: "flex", gap: 14 }}>
                <div
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: "50%",
                    background: "var(--teal-dim)",
                    color: "var(--teal)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 800,
                    fontSize: 13,
                    flex: "none",
                  }}
                >
                  {n}
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>{title}</div>
                  <div style={{ color: "var(--muted)", fontSize: 13 }}>{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 28 }}>
        <SubscribeForm
          initialPackage={initialPackage}
          identity={identity ? { name: identity.display_name, email: identity.email } : null}
        />
      </div>
    </div>
  );
}
