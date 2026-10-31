"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import SignOutButton from "./sign-out-button";
import ThemeToggle from "./theme-toggle";

export const navigation = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/ipos", label: "IPOs", icon: "ipo" },
  { href: "/plan", label: "Plan", icon: "plan" },
  { href: "/funds", label: "Funds", icon: "funds" },
  { href: "/applications", label: "Applications", icon: "applications" },
  { href: "/check-allotment", label: "Check Allotment", icon: "allotment" },
  { href: "/portfolio", label: "Portfolio", icon: "portfolio" },
  { href: "/gold", label: "Gold", icon: "gold" },
  { href: "/settings/investors", label: "Settings", icon: "settings" },
] as const;

function NavIcon({ name }: { name: (typeof navigation)[number]["icon"] }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return <svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true" {...common}>
    {name === "home" && <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M9 21v-7h6v7"/></>}
    {name === "ipo" && <><rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4M7 14h4M7 17h7"/></>}
    {name === "plan" && <><rect x="4" y="3" width="16" height="18" rx="2"/><path d="m8 12 2 2 5-5M8 18h8"/></>}
    {name === "funds" && <><rect x="3" y="6" width="18" height="15" rx="2"/><path d="M3 10h18M7 6V4a1 1 0 0 1 1-1h10"/><circle cx="17" cy="15" r="1"/></>}
    {name === "applications" && <><path d="M8 3h9l4 4v13a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M17 3v5h4M10 12h7M10 16h7"/></>}
    {name === "allotment" && <><circle cx="10" cy="10" r="7"/><path d="m15 15 6 6M7 10l2 2 4-4"/></>}
    {name === "portfolio" && <><path d="M3 20h18M5 16l5-5 4 3 5-7"/><path d="M16 7h3v3"/></>}
    {name === "gold" && <><path d="m7 5-4 14h18L17 5zM7 5h10M5 13h14"/><path d="M9 9h6"/></>}
    {name === "settings" && <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-1.86 1.86-.06-.06A1.7 1.7 0 0 0 16 18.4a1.7 1.7 0 0 0-1 1.56V20H9v-.04a1.7 1.7 0 0 0-1-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-1.86-1.86.06-.06A1.7 1.7 0 0 0 4.6 15 1.7 1.7 0 0 0 3.04 14H3v-4h.04A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.88L4.2 7.06 6.06 5.2l.06.06A1.7 1.7 0 0 0 8 5.6 1.7 1.7 0 0 0 9 4.04V4h6v.04A1.7 1.7 0 0 0 16 5.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 1.86 1.86-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.56 1H21v4h-.04A1.7 1.7 0 0 0 19.4 15z"/></>}
  </svg>;
}

export default function AppNav({ email, founderAdmin, localPreview, theme }: {
  email: string;
  founderAdmin: boolean;
  localPreview: boolean;
  theme: "light" | "dark";
}) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const active = (href: string) => href === "/" ? pathname === "/" : pathname.startsWith(href);


  return <>
    <aside className="app-sidebar" aria-label="Application sidebar">
      <Link className="app-brand" href="/"><span className="brand-symbol" aria-hidden="true">L</span><span>Lot<span>Neeti</span><small>IPO OPERATIONS</small></span></Link>
      <nav className="app-nav" aria-label="Primary">
        {navigation.map((item) => <Link key={item.href} href={item.href} aria-current={active(item.href) ? "page" : undefined}><span className="nav-icon"><NavIcon name={item.icon} /></span>{item.label}</Link>)}
      </nav>
      <div className="sidebar-footer">
        <ThemeToggle className="sidebar-theme-toggle" initialTheme={theme} />
        {founderAdmin && <a className="admin-link" href="/admin/">Founder Admin <span aria-hidden="true">↗</span></a>}
        <div className="account-menu"><div className="account-summary"><span className="account-avatar" aria-hidden="true">{email.slice(0, 1).toUpperCase()}</span><span className="account-copy"><strong>{localPreview ? "Local preview" : "Account"}</strong><small>{email}</small></span></div>{!localPreview && <div><SignOutButton /></div>}</div>
      </div>
    </aside>
    <header className="mobile-header"><Link className="app-brand" href="/"><span className="brand-symbol" aria-hidden="true">L</span><span>Lot<span>Neeti</span></span></Link><button className="mobile-menu-toggle" type="button" aria-expanded={menuOpen} aria-controls="mobile-overflow" onClick={() => setMenuOpen(!menuOpen)}>Menu</button></header>
    {menuOpen && <div className="mobile-overflow" id="mobile-overflow">{navigation.slice(4).map((item) => <Link key={item.href} href={item.href} onClick={() => setMenuOpen(false)}>{item.label}</Link>)}<ThemeToggle initialTheme={theme} />{founderAdmin && <a href="/admin/">Founder Admin</a>}<p>{localPreview ? "Local preview" : email}</p>{!localPreview && <SignOutButton />}</div>}
    <nav className="mobile-nav" aria-label="Mobile primary">{navigation.slice(0, 4).map((item) => <Link key={item.href} href={item.href} aria-current={active(item.href) ? "page" : undefined}><span aria-hidden="true"><NavIcon name={item.icon} /></span>{item.label}</Link>)}</nav>
  </>;
}
