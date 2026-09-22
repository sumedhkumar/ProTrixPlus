import { AuthExperience } from "@/components/AuthExperience";

/** Same page as /login - see AuthExperience; this route just opens it on the
 * create-account (free trial) tab. */
export default function TrialPage() {
  return <AuthExperience initialMode="signup" />;
}
