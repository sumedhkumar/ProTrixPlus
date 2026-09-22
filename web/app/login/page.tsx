import { AuthExperience } from "@/components/AuthExperience";

/** Same page as /trial - see AuthExperience; this route just opens it on the
 * sign-in tab. */
export default function LoginPage() {
  return <AuthExperience initialMode="signin" />;
}
