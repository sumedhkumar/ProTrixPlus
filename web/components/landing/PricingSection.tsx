import Link from "next/link";

const PACKAGES: {
  key: string;
  label: string;
  price: string;
  period: string;
  featured?: boolean;
  priceTBD?: boolean;
  note?: string;
  href: string;
  cta: string;
  features: string[];
}[] = [
  {
    key: "TRIAL_7D",
    label: "7-Day Free Trial",
    price: "Free",
    period: "for 7 days",
    note: "New users only",
    href: "/trial",
    cta: "Start Free Trial",
    features: ["Full dashboard access", "Live execution tracking", "No card required"],
  },
  {
    key: "PLAN_3M",
    label: "3-Month Plan",
    price: "$0",
    period: "/ 3 months",
    priceTBD: true,
    href: "/subscribe?package=PLAN_3M",
    cta: "Choose 3-Month",
    features: ["Everything in trial", "3 months of platform access", "Priority support"],
  },
  {
    key: "PLAN_6M",
    label: "6-Month Plan",
    price: "$0",
    period: "/ 6 months",
    featured: true,
    priceTBD: true,
    href: "/subscribe?package=PLAN_6M",
    cta: "Choose 6-Month",
    features: ["Everything in trial", "6 months of platform access", "Priority support"],
  },
  {
    key: "PLAN_12M",
    label: "1-Year Plan",
    price: "$0",
    period: "/ 12 months",
    priceTBD: true,
    href: "/subscribe?package=PLAN_12M",
    cta: "Choose 1-Year",
    features: ["Everything in trial", "12 months of platform access", "Priority support"],
  },
];

export function PricingSection() {
  return (
    <section className="landing-section" id="pricing">
      <div className="landing-section-head">
        <h2>Simple, Transparent Packages</h2>
        <p>
          Start with a free 7-day trial. Paid plan pricing is being finalized - submit your
          payment reference after transferring and our team confirms it by email.
        </p>
      </div>

      <div className="pricing-grid">
        {PACKAGES.map((p) => (
          <div key={p.key} className={`card pricing-card${p.featured ? " featured" : ""}`}>
            {p.featured ? (
              <span
                className="badge-pill badge-gradient"
                style={{ position: "absolute", top: -10, right: 16 }}
              >
                MOST POPULAR
              </span>
            ) : null}
            <div className="card-title">{p.label}</div>
            <div className="pricing-card-price">
              {p.price} <span className="period">{p.period}</span>
            </div>
            {p.priceTBD ? <span className="badge-pill badge-neutral">Pricing coming soon</span> : null}
            {p.note ? <span className="badge-pill badge-neutral">{p.note}</span> : null}
            <ul>
              {p.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <Link
              href={p.href}
              className="btn-primary"
              style={{
                textAlign: "center",
                padding: "10px 16px",
                borderRadius: 8,
                fontWeight: 700,
                fontSize: 13,
              }}
            >
              {p.cta}
            </Link>
          </div>
        ))}
      </div>
    </section>
  );
}
