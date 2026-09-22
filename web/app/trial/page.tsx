import { AuthExperience } from "@/components/AuthExperience";

// See the same line in app/login/page.tsx - reading process.env alone
// doesn't mark a route dynamic, so this was getting prerendered once at
// build time (env var not even set yet) and frozen forever after.
export const dynamic = "force-dynamic";

/** Same page as /login - see AuthExperience; this route just opens it on the
 * create-account (free trial) tab. Server Component (no "use client") so
 * this reads the real env var at request time - see GoogleSignInButton's
 * `clientId` doc for why NEXT_PUBLIC_ build-time inlining doesn't work here. */
export default function TrialPage() {
  return (
    <AuthExperience initialMode="signup" googleClientId={process.env.PROTRIX_GOOGLE_OAUTH_CLIENT_ID} />
  );
}
