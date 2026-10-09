"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import SignOutButton from "./sign-out-button";

export const navigation = [
  { href: "/", label: "Home", icon: "▦" },
  { href: "/ipos", label: "IPOs", icon: "◫" },
  { href: "/plan", label: "Plan", icon: "▤" },
  { href: "/funds", label: "Funds", icon: "◉" },
  { href: "/applications", label: "Applications", icon: "☷" },
  { href: "/portfolio", label: "Portfolio", icon: "▥" },
  { href: "/settings/investors", label: "Settings", icon: "⚙" },
] as const;

type Workspace = { id: string; name: string; role: string };

export default function AppNav({ email, workspaces, selectedId, founderAdmin, localPreview }: {
  email: string;
  workspaces: Workspace[];
  selectedId?: string;
  founderAdmin: boolean;
  localPreview: boolean;
}) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const active = (href: string) => href === "/" ? pathname === "/" : pathname.startsWith(href);
  const selectWorkspace = (id: string) => {
    document.cookie = `lotneeti_workspace=${encodeURIComponent(id)}; Path=/; SameSite=Lax; Max-Age=31536000`;
    window.location.reload();
  };

  return <>
    <aside className="app-sidebar" aria-label="Application sidebar">
      <Link className="app-brand" href="/"><span className="brand-symbol" aria-hidden="true">L</span><span>Lot<span>Neeti</span><small>IPO OPERATIONS</small></span></Link>
      <div className="workspace-control">
        <label htmlFor="workspace-select">Workspace</label>
        <select id="workspace-select" value={selectedId ?? ""} onChange={(event) => selectWorkspace(event.target.value)} disabled={workspaces.length === 0}>
          {workspaces.length === 0 ? <option value="">No workspace</option> : workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
        </select>
      </div>
      <nav className="app-nav" aria-label="Primary">
        {navigation.map((item) => <Link key={item.href} href={item.href} aria-current={active(item.href) ? "page" : undefined}><span className="nav-icon" aria-hidden="true">{item.icon}</span>{item.label}</Link>)}
      </nav>
      <div className="sidebar-footer">
        {founderAdmin && <a className="admin-link" href="/admin/">Founder Admin <span aria-hidden="true">↗</span></a>}
        <details className="account-menu"><summary><span className="account-avatar" aria-hidden="true">{email.slice(0, 1).toUpperCase()}</span><span className="account-copy"><strong>{localPreview ? "Local preview" : "Account"}</strong><small>{email}</small></span></summary>{!localPreview && <div><SignOutButton /></div>}</details>
      </div>
    </aside>
    <header className="mobile-header"><Link className="app-brand" href="/"><span className="brand-symbol" aria-hidden="true">L</span><span>Lot<span>Neeti</span></span></Link><button className="mobile-menu-toggle" type="button" aria-expanded={menuOpen} aria-controls="mobile-overflow" onClick={() => setMenuOpen(!menuOpen)}>Menu</button></header>
    {menuOpen && <div className="mobile-overflow" id="mobile-overflow"><label htmlFor="mobile-workspace-select">Workspace</label><select id="mobile-workspace-select" value={selectedId ?? ""} onChange={(event) => selectWorkspace(event.target.value)}>{workspaces.length === 0 ? <option value="">No workspace</option> : workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}</select>{navigation.slice(4).map((item) => <Link key={item.href} href={item.href} onClick={() => setMenuOpen(false)}>{item.label}</Link>)}{founderAdmin && <a href="/admin/">Founder Admin</a>}<p>{localPreview ? "Local preview" : email}</p>{!localPreview && <SignOutButton />}</div>}
    <nav className="mobile-nav" aria-label="Mobile primary">{navigation.slice(0, 4).map((item) => <Link key={item.href} href={item.href} aria-current={active(item.href) ? "page" : undefined}><span aria-hidden="true">{item.icon}</span>{item.label}</Link>)}</nav>
  </>;
}
