"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export interface TabDef {
  href: string;
  label: string;
  icon: string;
}

/** Collapsed icon-only rail by default (full viewport height, fixed to the
 * left edge) - hovering it expands to reveal each section's label, matching
 * the reference UI the user asked to match. Replaces the old horizontal
 * TabNav; the app-shell wrapper (dashboard/admin layout.tsx) adds a
 * matching left padding so page content never sits under this fixed rail. */
export function SidebarNav({ tabs, modeLabel }: { tabs: TabDef[]; modeLabel: string }) {
  const pathname = usePathname();
  return (
    <nav className="sidebar-nav" aria-label="Main navigation">
      <div className="sidebar-nav-links">
        {tabs.map((t) => {
          const active = pathname === t.href;
          return (
            <Link key={t.href} href={t.href} className={`sidebar-link${active ? " active" : ""}`}>
              <span className="sidebar-link-icon" aria-hidden>
                {t.icon}
              </span>
              <span className="sidebar-link-label">{t.label}</span>
            </Link>
          );
        })}
      </div>
      <div className="sidebar-nav-footer">
        <span className="sidebar-link-icon" aria-hidden>
          ◈
        </span>
        <span className="sidebar-link-label">{modeLabel} PORTAL</span>
      </div>
    </nav>
  );
}
