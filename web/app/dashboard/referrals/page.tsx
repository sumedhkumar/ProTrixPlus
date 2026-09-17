const REFERRED = [
  { name: "Elena Rostova", joined: "2026-03-01", status: "Active Subscriber", commission: "+$30.00" },
  { name: "David Chen", joined: "2026-04-10", status: "Active Subscriber", commission: "+$30.00" },
];

export default function ReferralsPage() {
  return (
    <>
      <h1>
        Referral Partner Program &amp; Rewards <span className="badge-pill badge-demo">DEMO</span>
      </h1>
      <p style={{ color: "var(--muted)", marginBottom: 20 }}>
        Illustrative data only - trigger condition, bonus amount, and payout mechanism
        haven&apos;t been confirmed yet (docs/FULL-BUILD-PLAN.md open question #6). This link and
        balance are not real.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginBottom: 20 }}>
        <div className="card">
          <div className="card-head">
            <span className="card-title">Your referral link</span>
            <span className="badge-pill badge-neutral">Code: DEMO_REF</span>
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <input readOnly value="https://protrixplus.example/join?ref=DEMO_REF" style={{ flex: 1 }} />
            <button className="secondary" disabled title="Demo only">
              Copy
            </button>
          </div>
          <p style={{ color: "var(--dim)", fontSize: 12, marginTop: 10 }}>
            When a trader registers using your link and is granted a strategy, the referral
            program (not yet built) would credit your bonus balance.
          </p>
        </div>
        <div className="card">
          <div className="card-head">
            <span className="card-title">Available credits</span>
          </div>
          <div className="stat-value">$60.00</div>
          <div className="stat-sub">
            <span>Total lifetime earned: $60.00</span>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <span className="card-title">Referred traders</span>
          <span className="badge-pill badge-neutral">{REFERRED.length} referred</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Referred trader</th>
                <th>Joined date</th>
                <th>Strategy subscribed</th>
                <th>Commission earned</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {REFERRED.map((r) => (
                <tr key={r.name}>
                  <td style={{ fontWeight: 700 }}>{r.name}</td>
                  <td>{r.joined}</td>
                  <td>
                    <span className="badge-pill badge-green">{r.status}</span>
                  </td>
                  <td style={{ color: "var(--ok)" }}>{r.commission}</td>
                  <td>
                    <span className="badge-pill badge-green">CREDITED</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
