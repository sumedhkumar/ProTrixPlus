import Link from "next/link";

import type { Identity } from "@/lib/api";

export function IdentityBar({ identity }: { identity: Identity }) {
  return (
    <div className="topbar">
      <strong>Protrixplus</strong>
      <span className="badge">MVP</span>
      <span className="grow" />
      <span data-testid="identity">
        {identity.display_name} &middot; <code data-testid="identity-role">{identity.role}</code>
      </span>
      {identity.role === "SUPER_ADMIN" ? <Link href="/admin">Admin</Link> : null}
      <Link href="/dashboard">Dashboard</Link>
      <a href="/logout">Sign out</a>
    </div>
  );
}
