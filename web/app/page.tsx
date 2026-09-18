import { redirect } from "next/navigation";

import { LandingPage } from "@/components/landing/LandingPage";
import { getClaims } from "@/lib/auth";
import { homePathForRole } from "@/lib/roles";

export default function Home() {
  const claims = getClaims();
  if (claims) redirect(homePathForRole(claims.role));
  return <LandingPage />;
}
