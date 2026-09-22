const FAQS: [string, string][] = [
  [
    "Is the 7-day trial really free?",
    "Yes. Sign up with your name, email, and phone - no card required - and you get full dashboard access for 7 days.",
  ],
  [
    "How does billing work if there's no payment gateway?",
    "You transfer payment to ProTrixPlus directly (bank transfer or UPI) and submit the transaction / UTR reference. Our team confirms it by email, usually within one business day.",
  ],
  [
    "Is my MT5 password stored anywhere?",
    "No. Broker credentials are held behind short-lived, scoped handles and are never returned to the browser, logged, or stored as plaintext.",
  ],
  [
    "What happens when my trial or plan expires?",
    "You get a 1-day grace period with a renewal reminder. After that, dashboard access pauses (nothing is deleted) until you renew.",
  ],
  [
    "Can I switch plans or renew early?",
    "Yes - renewing while your current plan is still active extends it from your existing end date, so you never lose time you already paid for.",
  ],
];

export function FaqSection() {
  return (
    <section className="landing-section" id="faq">
      <div className="landing-section-head">
        <h2>Frequently Asked Questions</h2>
      </div>

      <div style={{ maxWidth: 760, margin: "0 auto", display: "grid", gap: 10 }}>
        {FAQS.map(([q, a]) => (
          <details key={q} className="card faq-item">
            <summary>{q}</summary>
            <p>{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
