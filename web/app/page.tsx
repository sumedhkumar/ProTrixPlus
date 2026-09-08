import { redirect } from "next/navigation";

import { getClaims } from "@/lib/auth";
import { homePathForRole } from "@/lib/roles";

export default function Home() {
  const claims = getClaims();
  redirect(claims ? homePathForRole(claims.role) : "/login");
}
