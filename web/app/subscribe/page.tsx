import { AuthShell } from "@/components/AuthShell";
import { PaymentInstructions } from "@/components/PaymentInstructions";
import { SubscribeForm } from "@/components/SubscribeForm";
import { apiFetch, type Identity, type PaymentInstructionsView } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { homePathForRole } from "@/lib/roles";

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
    <AuthShell
      right={
        <a
          href={identity ? homePathForRole(identity.role) : "/login"}
          className="btn-ghost"
          style={{ padding: "8px 16px" }}
        >
          {identity ? "Back to dashboard →" : "Sign In →"}
        </a>
      }
    >
    <div className="login-split">
      <div>
        <span className="badge-pill badge-teal">💳 Payment Confirmation</span>
        <h1 className="hero-heading" style={{ fontSize: 34 }}>
          {searchParams.renew ? "Renew your subscription" : "Activate a paid plan"}
        </h1>
        <p className="hero-copy" style={{ marginBottom: 28, maxWidth: 440 }}>
          There&apos;s no payment gateway yet - transfer payment to ProTrixPlus, then submit your
          transaction / UTR reference below.
        </p>
        {identity?.subscription?.hard_blocked ? (
          <div className="card" style={{ borderColor: "rgba(240,87,107,0.35)", marginBottom: 24 }}>
            <p style={{ fontSize: 13, color: "var(--bad)", margin: 0 }}>
              Your subscription has expired. Submit a renewal below to restore dashboard access.
            </p>
          </div>
        ) : null}

        <PaymentInstructions instructions={instructions} />

        <div className="inline-divider">
          <span className="inline-divider-label">What happens next</span>
          <div className="steps-list">
            {STEPS.map(([n, title, desc], i) => (
              <div key={n} className="step-row">
                <div className="step-rail">
                  <span className="step-num">{n}</span>
                  {i < STEPS.length - 1 ? <span className="step-line" /> : null}
                </div>
                <div>
                  <div className="step-title">{title}</div>
                  <div className="step-desc">{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="form-panel">
        <SubscribeForm
          initialPackage={initialPackage}
          identity={identity ? { name: identity.display_name, email: identity.email } : null}
        />
      </div>
    </div>
    </AuthShell>
  );
}
