"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AuthShell } from "@/components/AuthShell";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";
import { homePathForRole, type Role } from "@/lib/roles";

export type AuthMode = "signin" | "signup";

interface Alert {
  tone: "error" | "info";
  message: string;
  action?: { label: string; onClick: () => void };
  /** No close button while true - there's nothing to dismiss back to, the
   * request is still in flight. */
  loading?: boolean;
}

function AuthAlert({ alert, onDismiss }: { alert: Alert; onDismiss: () => void }) {
  return (
    <div className={`auth-alert ${alert.tone}`} role="alert">
      <span className="auth-alert-icon">
        {alert.loading ? (
          <span className="auth-alert-spinner" aria-hidden />
        ) : alert.tone === "error" ? (
          "!"
        ) : (
          "i"
        )}
      </span>
      <div className="auth-alert-body">
        <p className="auth-alert-message">{alert.message}</p>
        {alert.action ? (
          <button type="button" className="auth-alert-action" onClick={alert.action.onClick}>
            {alert.action.label} →
          </button>
        ) : null}
      </div>
      {alert.loading ? null : (
        <button type="button" className="auth-alert-close" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  );
}

const DEMO_PASSWORD = "Demo12345!";
const DEMO_PROFILES: { name: string; email: string; role: "ADMIN" | "CLIENT" }[] = [
  { name: "Alex Vance", email: "alex.vance@protrixplus.test", role: "ADMIN" },
];

interface Feature {
  icon: string;
  color: "teal" | "purple";
  title: string;
  desc: string;
}

const PITCH: Record<
  AuthMode,
  { badge: string; heading: string; copy: string; features: Feature[] }
> = {
  signin: {
    badge: "🛡 Multi-User Fan-Out Architecture",
    heading: "Automated MT5 Execution for Modern Quant Traders.",
    copy: "Connect TradingView alerts to multiple client MT5 accounts, with per-client lot-size entitlement and admin-controlled strategy access.",
    features: [
      {
        icon: "🖥",
        color: "teal",
        title: "Dual Login Security (Email or Google)",
        desc: "Sign in with a password or continue with Google - same account either way.",
      },
      {
        icon: "📡",
        color: "purple",
        title: "Idempotent Webhook Gateway",
        desc: "Signal deduplication (signal_id / idempotency_key) blocks duplicate signal execution - this one is real, not marketing copy.",
      },
      {
        icon: "🔑",
        color: "purple",
        title: "Investor-Grade Security",
        desc: "MT5 credentials are never stored as plaintext passwords here - real broker connectivity is pending MetaApi.cloud credentials.",
      },
    ],
  },
  signup: {
    badge: "🛡 Free 7-Day Trial",
    heading: "Try ProTrixPlus free for 7 days.",
    copy: "No password to create, no card required. We'll email you a temporary password - you'll set your own the first time you log in.",
    features: [
      {
        icon: "⏱",
        color: "purple",
        title: "No Card Required",
        desc: "Full 7-day access to the dashboard and live execution tracking - nothing to enter up front.",
      },
      {
        icon: "🧩",
        color: "teal",
        title: "Multiple Strategies, One Dashboard",
        desc: "Browse the strategy marketplace and pick what fits your risk appetite - not locked into one signal source.",
      },
      {
        icon: "🔒",
        color: "purple",
        title: "Set Your Own Password on First Login",
        desc: "You choose a permanent password the first time you sign in - nothing stored in your inbox afterward.",
      },
    ],
  },
};

/** The whole pre-signin experience: /login mounts it on "signin", /trial on
 * "signup". Both are the same page - toggling swaps the pitch column and the
 * form in place (and the URL with it) rather than navigating, so the
 * transition can animate. Creating an account *is* starting the free trial:
 * there is one signup path (name/email/phone -> temp password emailed). */
interface AuthExperienceProps {
  initialMode: AuthMode;
  /** Read server-side and passed down - see GoogleSignInButton's `clientId`
   * doc for why this isn't read from process.env directly in client code. */
  googleClientId: string | undefined;
}

export function AuthExperience({ initialMode, googleClientId }: AuthExperienceProps) {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [hasToggled, setHasToggled] = useState(false);
  const [animating, setAnimating] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [alert, setAlert] = useState<Alert | null>(null);
  const [signedUpEmail, setSignedUpEmail] = useState<string | null>(null);
  const googleEnabled = Boolean(googleClientId);
  const [showPassword, setShowPassword] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  const bodyRef = useRef<HTMLDivElement>(null);
  const [bodyHeight, setBodyHeight] = useState<number>();
  const animationTimer = useRef<ReturnType<typeof setTimeout>>();

  // Measure the active panel body so .auth-swap can transition between the
  // two modes' heights instead of snapping.
  useEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    const measure = () => setBodyHeight(el.offsetHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [mode, signedUpEmail]);

  useEffect(() => () => clearTimeout(animationTimer.current), []);

  // Keep the URL honest without a real navigation - a router.replace here
  // would remount the page and kill the animation mid-flight.
  useEffect(() => {
    const path = mode === "signin" ? "/login" : "/trial";
    if (window.location.pathname !== path) {
      window.history.replaceState(null, "", path);
    }
  }, [mode]);

  const switchMode = useCallback(
    (next: AuthMode) => {
      if (next === mode) return;
      setHasToggled(true);
      setAnimating(true);
      setAlert(null);
      setMode(next);
      clearTimeout(animationTimer.current);
      animationTimer.current = setTimeout(() => setAnimating(false), 520);
    },
    [mode],
  );

  const routeAfterAuth = useCallback(
    (role: Role, mustChangePassword: boolean) => {
      if (mustChangePassword) {
        router.push("/set-password");
      } else {
        router.push(homePathForRole(role));
      }
      router.refresh();
    },
    [router],
  );

  async function doLogin(authEmail: string, authPassword: string) {
    setBusy("signin");
    setAlert(null);
    const res = await fetch("/api/auth-session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "login", email: authEmail, password: authPassword }),
    });
    if (!res.ok) {
      setBusy(null);
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setAlert({ tone: "error", message: body.detail ?? `sign-in failed (${res.status})` });
      return;
    }
    const body = (await res.json()) as { role: Role; must_change_password: boolean };
    routeAfterAuth(body.role, body.must_change_password);
  }

  async function doSignup() {
    setBusy("signup");
    setAlert(null);
    const res = await fetch("/api/trial-signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email }),
    });
    setBusy(null);
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setAlert({ tone: "error", message: body.detail ?? `signup failed (${res.status})` });
      return;
    }
    setSignedUpEmail(email);
  }

  async function signInMock(role: Role) {
    setBusy(role);
    setAlert(null);
    const res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!res.ok) {
      setBusy(null);
      setAlert({ tone: "error", message: `sign-in failed (${res.status})` });
      return;
    }
    router.push(homePathForRole(role));
    router.refresh();
  }

  async function postGoogleCredential(endpoint: string, credential: string) {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential }),
    });
    const body = (await res.json().catch(() => ({}))) as {
      detail?: string;
      email?: string;
      role?: Role;
      must_change_password?: boolean;
    };
    return { ok: res.ok, status: res.status, body };
  }

  // googleSignIn and googleSignUp each offer to retry as the other on the
  // matching error (404 "no account" / 409 "already exists"), reusing the
  // same already-verified credential - the user only clicks the Google
  // button once, not once per guess at which tab they needed.
  async function googleSignIn(credential: string) {
    setBusy("google");
    setAlert({ tone: "info", message: "Signing you in with Google...", loading: true });
    const { ok, status, body } = await postGoogleCredential("/api/google-login", credential);
    if (ok) {
      routeAfterAuth(body.role ?? "USER", body.must_change_password ?? false);
      return;
    }
    setBusy(null);
    if (status === 404) {
      setAlert({
        tone: "info",
        message: "No ProTrixPlus account exists yet for that Google account.",
        action: {
          label: "Sign up instead",
          onClick: () => {
            switchMode("signup");
            void googleSignUp(credential);
          },
        },
      });
      return;
    }
    setAlert({ tone: "error", message: body.detail ?? `Google sign-in failed (${status})` });
  }

  async function googleSignUp(credential: string) {
    setBusy("google");
    setAlert({ tone: "info", message: "Setting up your free trial account...", loading: true });
    const { ok, status, body } = await postGoogleCredential("/api/google-signup", credential);
    setBusy(null);
    if (ok) {
      setAlert(null);
      setSignedUpEmail(body.email ?? "");
      return;
    }
    if (status === 409) {
      setAlert({
        tone: "info",
        message: "An account already exists for that Google email.",
        action: {
          label: "Sign in instead",
          onClick: () => {
            switchMode("signin");
            void googleSignIn(credential);
          },
        },
      });
      return;
    }
    setAlert({ tone: "error", message: body.detail ?? `Google sign-up failed (${status})` });
  }

  // Plain (non-memoized) on purpose: GoogleSignInButton only reads this via a
  // ref it keeps in sync every render, so it never needs a stable identity.
  function handleGoogleCredential(credential: string) {
    void (mode === "signin" ? googleSignIn(credential) : googleSignUp(credential));
  }

  const pitch = PITCH[mode];
  const labelStyle = {
    fontSize: 12,
    color: "var(--muted)",
    display: "block",
    marginBottom: 6,
  } as const;

  return (
    <AuthShell>
      <div className="login-split">
        <div
          key={`pitch-${mode}`}
          className={hasToggled ? "auth-swap-pitch" : undefined}
        >
          <span className="badge-pill badge-teal">{pitch.badge}</span>
          <h1 className="hero-heading">{pitch.heading}</h1>
          <p className="hero-copy">{pitch.copy}</p>

          <div className="feature-list">
            {pitch.features.map((f) => (
              <div key={f.title} className="feature-row">
                <div className={`feature-icon ${f.color}`}>{f.icon}</div>
                <div>
                  <div className="feature-row-title">{f.title}</div>
                  <div className="feature-row-desc">{f.desc}</div>
                </div>
              </div>
            ))}
          </div>

          {mode === "signin" ? (
            <div className="inline-divider">
              <span className="inline-divider-label">
                ✨ 1-Click Demo Profiles - real accounts, instant sign-in
              </span>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                {DEMO_PROFILES.map((p) => (
                  <button
                    key={p.email}
                    type="button"
                    className="demo-profile-btn"
                    disabled={busy !== null}
                    onClick={() => {
                      setEmail(p.email);
                      setPassword(DEMO_PASSWORD);
                      void doLogin(p.email, DEMO_PASSWORD);
                    }}
                  >
                    <span className="dot green" /> {busy === "signin" ? "..." : p.name}{" "}
                    <span className="role-tag">({p.role})</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="form-panel">
          {signedUpEmail !== null ? (
            <div>
              <div className="card-head">
                <span className="card-title">✓ Account created</span>
              </div>
              <p style={{ color: "var(--fg)", fontSize: 14, marginBottom: 8 }}>
                Check <strong>{signedUpEmail}</strong> for your temporary password.
              </p>
              <p
                style={{
                  color: "var(--muted)",
                  fontSize: 13,
                  marginBottom: googleEnabled ? 8 : 20,
                }}
              >
                Log in with it, then you&apos;ll be asked to set your own password.
              </p>
              {googleEnabled ? (
                <p style={{ color: "var(--warn)", fontSize: 12.5, marginBottom: 20 }}>
                  ⚠ &quot;Continue with Google&quot; won&apos;t work until after that first
                  password login.
                </p>
              ) : null}
              <button
                type="button"
                className="btn-primary"
                style={{ padding: "10px 16px" }}
                onClick={() => {
                  setSignedUpEmail(null);
                  setPassword("");
                  switchMode("signin");
                }}
              >
                Go to Sign In →
              </button>
            </div>
          ) : (
            <>
              <div className="auth-tab-group" style={{ marginBottom: 20 }}>
                <button
                  type="button"
                  className={`auth-tab ${mode === "signin" ? "active" : ""}`}
                  onClick={() => switchMode("signin")}
                >
                  ▸ Sign In
                </button>
                <button
                  type="button"
                  className={`auth-tab ${mode === "signup" ? "active" : ""}`}
                  onClick={() => switchMode("signup")}
                >
                  + Start Free Trial
                </button>
              </div>

              {alert ? (
                <div style={{ marginBottom: 16 }}>
                  <AuthAlert alert={alert} onDismiss={() => setAlert(null)} />
                </div>
              ) : null}

              <div
                className="auth-swap"
                data-animating={animating ? "true" : undefined}
                style={hasToggled ? { height: bodyHeight } : undefined}
              >
                <div
                  ref={bodyRef}
                  key={`body-${mode}`}
                  className={hasToggled ? "auth-swap-content" : undefined}
                >
                  {mode === "signin" ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void doLogin(email, password);
                      }}
                      style={{ display: "grid", gap: 14 }}
                    >
                      <div>
                        <label style={labelStyle}>Email</label>
                        <input
                          type="email"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          placeholder="name@domain.com"
                          required
                          style={{ width: "100%" }}
                        />
                      </div>

                      <div>
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            marginBottom: 6,
                          }}
                        >
                          <label style={{ fontSize: 12, color: "var(--muted)" }}>Password</label>
                          <Link href="/forgot-password" className="card-link">
                            Forgot password?
                          </Link>
                        </div>
                        <div style={{ position: "relative" }}>
                          <input
                            type={showPassword ? "text" : "password"}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            minLength={8}
                            required
                            style={{ width: "100%", paddingRight: 56 }}
                          />
                          <button
                            type="button"
                            onClick={() => setShowPassword((v) => !v)}
                            style={{
                              position: "absolute",
                              right: 4,
                              top: 4,
                              background: "none",
                              color: "var(--dim)",
                              fontSize: 11,
                              fontWeight: 700,
                              padding: "6px 8px",
                            }}
                          >
                            {showPassword ? "Hide" : "Show"}
                          </button>
                        </div>
                      </div>

                      <label
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          fontSize: 13,
                          color: "var(--muted)",
                        }}
                      >
                        <input type="checkbox" defaultChecked style={{ width: "auto" }} />
                        Keep me signed in
                      </label>

                      <div className="auth-divider">or</div>
                      <GoogleSignInButton
                        clientId={googleClientId}
                        onCredential={handleGoogleCredential}
                        disabled={busy !== null}
                      />

                      <button
                        type="submit"
                        className="btn-primary"
                        disabled={busy !== null}
                        style={{ justifyContent: "center", padding: 12 }}
                      >
                        {busy === "signin" ? "..." : "Sign In to Terminal →"}
                      </button>

                      <div className="inline-divider">
                        <span className="inline-divider-label">
                          Dev/testing only - mock identity, no password
                        </span>
                        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                          {(
                            [
                              "USER",
                              "SUPER_ADMIN",
                              "OPERATIONS_ADMIN",
                              "STRATEGY_ADMIN",
                              "FINANCE_ADMIN",
                              "AUDITOR",
                            ] as const
                          ).map((mockRole) => (
                            <button
                              key={mockRole}
                              type="button"
                              className="secondary"
                              onClick={() => void signInMock(mockRole)}
                              disabled={busy !== null}
                            >
                              Mock {mockRole}
                            </button>
                          ))}
                        </div>
                      </div>
                    </form>
                  ) : (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void doSignup();
                      }}
                      style={{ display: "grid", gap: 14 }}
                    >
                      <div>
                        <label style={labelStyle}>Name</label>
                        <input
                          value={name}
                          onChange={(e) => setName(e.target.value)}
                          required
                          style={{ width: "100%" }}
                        />
                      </div>

                      <div>
                        <label style={labelStyle}>Email</label>
                        <input
                          type="email"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          placeholder="name@domain.com"
                          required
                          style={{ width: "100%" }}
                        />
                      </div>

                      <div className="auth-divider">or</div>
                      <GoogleSignInButton
                        clientId={googleClientId}
                        onCredential={handleGoogleCredential}
                        disabled={busy !== null}
                      />

                      <button
                        type="submit"
                        className="btn-primary"
                        disabled={busy !== null}
                        style={{ justifyContent: "center", padding: 12 }}
                      >
                        {busy === "signup" ? "..." : "Start Free Trial →"}
                      </button>
                    </form>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </AuthShell>
  );
}
