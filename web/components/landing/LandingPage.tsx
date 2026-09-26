import Link from "next/link";

import { AppFooter } from "@/components/AppFooter";
import { BrandMark } from "@/components/BrandMark";

import { FaqSection } from "./FaqSection";
import { LandingHero } from "./LandingHero";
import { PricingSection } from "./PricingSection";
import { SecuritySection } from "./SecuritySection";

const NAV_LINKS: [string, string][] = [
  ["#security", "Security"],
  ["#pricing", "Pricing"],
  ["#faq", "FAQ"],
];

export function LandingPage() {
  return (
    <div className="auth-shell">
      <div className="auth-shell-glow" aria-hidden />
      <header className="landing-nav">
        <div className="landing-nav-inner">
          <BrandMark />
          <div style={{ flex: 1 }} />
          <nav style={{ display: "flex", gap: 20 }}>
            {NAV_LINKS.map(([href, label]) => (
              <a
                key={href}
                href={href}
                style={{ fontSize: 13, color: "var(--muted)", textDecoration: "none" }}
              >
                {label}
              </a>
            ))}
          </nav>
          <Link href="/login" className="btn-ghost" style={{ padding: "8px 16px" }}>
            Sign In
          </Link>
          <Link href="/trial" className="btn-primary" style={{ padding: "8px 16px" }}>
            Start Free Trial
          </Link>
        </div>
      </header>

      <LandingHero />
      <SecuritySection />
      <PricingSection />
      <FaqSection />

      <section className="landing-cta">
        <h2>Ready to automate your execution?</h2>
        <p>Start your free 7-day trial - no card required, set up in under a minute.</p>
        <Link href="/trial" className="btn-primary" style={{ padding: "12px 24px" }}>
          Start Free 7-Day Trial →
        </Link>
      </section>

      <AppFooter />
    </div>
  );
}
