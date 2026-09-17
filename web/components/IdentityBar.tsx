"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";

import { Brand, Icon, type IconName } from "@/components/Icon";
import type { Identity } from "@/lib/api";

export function IdentityBar({ identity }: { identity: Identity | null }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const links: { href: string; label: string; icon: IconName }[] = [
    ...(identity ? [{ href: "/dashboard", label: "Dashboard", icon: "grid" as const }] : []),
    { href: "/marketplace", label: "Marketplace", icon: "layers" },
    ...(identity?.role === "SUPER_ADMIN" ? [{ href: "/admin", label: "Admin", icon: "shield" as const }] : []),
  ];
  const current = links.find((link) => link.href === pathname)?.label ?? "Workspace";
  const initials = identity?.display_name.split(/\s+/).filter(Boolean).slice(0, 2).map((name) => name[0]).join("");

  function closeMenu() {
    setMenuOpen(false);
    menuButton.current?.focus();
  }

  return <>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="topbar">
      <button ref={menuButton} className="menu-toggle secondary" type="button" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen} aria-controls="workspace-navigation" onClick={() => setMenuOpen(!menuOpen)} onKeyDown={(event) => { if (event.key === "Escape") closeMenu(); }}><Icon name={menuOpen ? "close" : "menu"} /></button>
      <div className="breadcrumb"><span>Workspace</span><span aria-hidden="true">/</span><strong>{current}</strong></div>
      <span className="grow" />
      {identity ? <div className="identity" data-testid="identity"><span className="identity-avatar" aria-hidden="true">{initials}</span><div><strong>{identity.display_name}</strong><code data-testid="identity-role">{identity.role}</code></div></div> : <Link href="/login" className="button-link secondary">Sign in <Icon name="arrow" size={16} /></Link>}
    </header>
    <aside className={`sidebar${menuOpen ? " sidebar-open" : ""}`} onKeyDown={(event) => { if (event.key === "Escape") closeMenu(); }}>
      <Link href={identity ? "/dashboard" : "/marketplace"} className="brand-link" aria-label="ProTrixPlus home" onClick={() => setMenuOpen(false)}><Brand /></Link>
      <span className="nav-label">Workspace</span>
      <nav id="workspace-navigation" className="sidebar-nav" aria-label="Main navigation">
        {links.map((link) => <Link key={link.href} href={link.href} className={`nav-link${pathname === link.href ? " nav-link-active" : ""}`} aria-current={pathname === link.href ? "page" : undefined} onClick={() => setMenuOpen(false)}><Icon name={link.icon} /><span>{link.label}</span>{pathname === link.href ? <span className="nav-indicator" /> : null}</Link>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="workspace-note"><span className="workspace-note-icon"><Icon name="activity" /></span><strong>Strategy to execution</strong><p>TradingView signals.<br />Your dedicated MT5 account.</p><span className="workspace-note-line" /></div>
        {identity ? <a className="nav-link signout-link" href="/logout"><Icon name="logout" /><span>Sign out</span></a> : <Link className="nav-link" href="/login"><Icon name="user" /><span>Sign in</span></Link>}
        <span className="sidebar-caption">ProTrixPlus · Trading workspace</span>
      </div>
    </aside>
  </>;
}
