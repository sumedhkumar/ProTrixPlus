import { AuthExperience } from "@/components/AuthExperience";

// Reading process.env alone doesn't mark a route dynamic - Next prerendered
// this as static HTML at *build* time (before the runtime env var even
// exists) and served that frozen page forever after. force-dynamic makes it
// render per-request instead, same reason as the Dockerfile/prop plumbing.
export const dynamic = "force-dynamic";

/** Same page as /trial - see AuthExperience; this route just opens it on the
 * sign-in tab. Server Component (no "use client") so this reads the real
 * env var at request time - see GoogleSignInButton's `clientId` doc for why
 * NEXT_PUBLIC_ build-time inlining doesn't work here. */
export default function LoginPage() {
  return (
    <AuthExperience initialMode="signin" googleClientId={process.env.PROTRIX_GOOGLE_OAUTH_CLIENT_ID} />
  );
}
