"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export interface TabDef {
  href: string;
  label: string;
  icon: string;
}

export function TabNav({ tabs, modeLabel }: { tabs: TabDef[]; modeLabel: string }) {
  const pathname = usePathname();
  return (
    <nav className="tabnav">
      <div className="tabnav-inner">
        {tabs.map((t) => {
          const active = pathname === t.href;
          return (
            <Link key={t.href} href={t.href} className={`tab-link${active ? " active" : ""}`}>
              <span aria-hidden>{t.icon}</span> {t.label}
            </Link>
          );
        })}
        <div className="tabnav-right">
          Active Mode: <span className="badge-pill badge-blue">{modeLabel} PORTAL</span>
        </div>
      </div>
    </nav>
  );
}
