import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "@/lib/backend";
import { formatInr } from "@/lib/money";
import { selectedWorkspace } from "@/lib/workspace";
import { EmptyState, MetricCard, PageHeader, SectionHeading, StatusBadge } from "@/components/ui";
import LiveSyncButton from "./live-sync-button";
import LandingPage from "./landing";

export const dynamic = "force-dynamic";

type CapitalLine = { balance: string; blocked: string; planned: string; available: string };
type Capital = CapitalLine & { by_bank?: Record<string, CapitalLine> };
type Operations = { active_ipos: number; applications: number; pending_mandates: number; allotment_wins: number; realized_gains: string };
type IPO = { id: string; issuer_name: string; issue_type: string; status: string; close_date: string; current_gmp_percent: string | null; current_gmp_observed_at: string | null };
type Decision = { ipo: string; selected: boolean; mode: string };
type Bank = { id: string; bank_name: string; account_masked: string; current_balance: string };
type Application = { id: string; ipo_name: string; applicant_name: string; status: string };
type Payment = { id: string; name: string; next_due_date: string; active: boolean; amount: string };
type Workspace = { id: string; name: string };
type FeedStatus = { provider: string; founder: boolean; can_sync: boolean; last_success_at: string | null; status: string };

async function getData<T>(path: string, cookieHeader: string): Promise<T | null> {
  try {
    const response = await fetch(backendUrl(path), { headers: { cookie: cookieHeader }, cache: "no-store" });
    return response.ok ? await response.json() as T : null;
  } catch { return null; }
}

function daysUntil(date: string): number {
  const today = new Date().toISOString().slice(0, 10);
  return Math.ceil((Date.parse(`${date}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86400000);
}
function modeLabel(mode: string): string {
  return ({ RETAIL_ONLY: "Retail Only", RETAIL_PLUS_SHNI: "Retail + sHNI", SHNI_PREFERRED: "sHNI Preferred", CUSTOM: "Custom" } as Record<string, string>)[mode] ?? "Retail Only";
}

export default async function HomePage() {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) return <LandingPage />;
  const workspaces = await getData<Workspace[]>("workspaces/", cookieHeader);
  if (!workspaces) redirect("/sign-in");
  const workspace = await selectedWorkspace(workspaces);
  if (!workspace) return <main className="page"><div className="shell home-shell"><PageHeader eyebrow="Overview" title="Operations dashboard" description="Your IPO activity and available money in one place." /><EmptyState title="Create a workspace to begin" detail="Add your investors and bank accounts, then select IPOs to plan applications." action={<Link className="button-link" href="/settings/investors">Set up workspace</Link>} /></div></main>;
  const prefix = `workspaces/${workspace.id}`;
  const [capital, operations, ipos, decisions, banks, applications, feed] = await Promise.all([
    getData<Capital>(`${prefix}/capital/`, cookieHeader),
    getData<Operations>(`${prefix}/operations/`, cookieHeader),
    getData<IPO[]>("ipos/", cookieHeader),
    getData<Decision[]>(`${prefix}/ipo-decisions/`, cookieHeader),
    getData<Bank[]>(`${prefix}/banks/`, cookieHeader),
    getData<Application[]>(`${prefix}/applications/`, cookieHeader),
    getData<FeedStatus>("ipos/live-sync/", cookieHeader),
  ]);
  const paymentLists = await Promise.all((banks ?? []).map((bank) => getData<Payment[]>(`${prefix}/banks/${bank.id}/recurring-debits/`, cookieHeader)));
  const payments = paymentLists.flatMap((items) => items ?? []);
  const selected = new Map((decisions ?? []).map((item) => [item.ipo, item]));
  const featured = (ipos ?? []).filter((ipo) => ipo.status === "OPEN" || selected.get(ipo.id)?.selected).slice(0, 6);
  const actions: { title: string; detail: string; href: string; tone: "warning" | "danger" | "info" }[] = [];
  for (const ipo of ipos ?? []) {
    const days = daysUntil(ipo.close_date);
    if (ipo.status === "OPEN" && days >= 0 && days <= 2) actions.push({ title: `${ipo.issuer_name} closes ${days === 0 ? "today" : `in ${days} days`}`, detail: "Review your selection and plan before closing.", href: "/ipos", tone: "warning" });
  }
  for (const application of applications ?? []) {
    if (application.status === "PLANNED") actions.push({ title: `${application.applicant_name}: application not submitted`, detail: application.ipo_name, href: "/applications", tone: "info" });
    if (application.status === "SUBMITTED") actions.push({ title: `${application.applicant_name}: mandate pending`, detail: application.ipo_name, href: "/applications", tone: "warning" });
    if (application.status === "BLOCKED") actions.push({ title: `${application.applicant_name}: result awaiting entry`, detail: application.ipo_name, href: "/applications", tone: "info" });
  }
  for (const payment of payments) {
    const days = daysUntil(payment.next_due_date);
    if (payment.active && days >= 0 && days <= 3) actions.push({ title: `${payment.name} scheduled ${days === 0 ? "today" : `in ${days} days`}`, detail: `${formatInr(payment.amount)} will affect bank funds.`, href: "/funds", tone: "warning" });
  }

  return <main className="page"><div className="shell home-shell">
    <PageHeader eyebrow="Overview" title="Operations dashboard" description={workspace.name} action={<Link className="button-link" href="/plan">Review plan <span aria-hidden="true">↗</span></Link>} />
    <div className="market-feed-status"><div><strong>IPO market data · InvestorGain</strong><small>{feed?.last_success_at ? `Last synced ${new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(feed.last_success_at))} IST` : "Waiting for the first successful sync"}{feed?.status === "ERROR" ? " · Latest attempt failed" : ""}</small></div>{feed?.can_sync ? <LiveSyncButton /> : feed?.founder ? <a href="/admin/login/?next=/">Verify as founder to enable Live sync</a> : null}</div>
    {!capital || !operations ? <div className="plan-error" role="alert">Dashboard data is temporarily unavailable. <Link href="/">Retry</Link></div> : <>
      <section className="metric-grid" aria-label="Money overview">
        <MetricCard label="Total Balance" value={formatInr(capital.balance)} note="Across your banks" href="/funds" />
        <MetricCard label="Blocked" value={formatInr(capital.blocked)} note="Active mandates" tone="warning" href="/applications" />
        <MetricCard label="Planned" value={formatInr(capital.planned)} note="Latest saved plan" href="/plan" />
        <MetricCard label="Available" value={formatInr(capital.available)} note="Free for applications" tone="accent" href="/funds" />
      </section>
      <section className="operations-grid" aria-label="Activity overview">
        <MetricCard label="Open IPOs" value={operations.active_ipos} href="/ipos" />
        <MetricCard label="Selected IPOs" value={(decisions ?? []).filter((item) => item.selected).length} href="/ipos" />
        <MetricCard label="Applications" value={operations.applications} href="/applications" />
        <MetricCard label="Pending Mandates" value={operations.pending_mandates} tone="warning" href="/applications" />
        <MetricCard label="Allotment Wins" value={operations.allotment_wins} href="/applications" />
        <MetricCard label="Realized Profit" value={formatInr(operations.realized_gains)} tone="positive" href="/portfolio" />
      </section>
    </>}
    <div className="home-content-grid">
      <section className="home-panel"><SectionHeading title="Open & selected IPOs" detail="Published issues and your current choices" action={<Link href="/ipos">View all IPOs →</Link>} />
        {featured.length === 0 ? <EmptyState title="No IPOs are available from configured providers yet." detail="Published IPOs will appear here when data is available." /> : <ul className="home-ipo-list">{featured.map((ipo) => { const choice = selected.get(ipo.id); const days = daysUntil(ipo.close_date); return <li key={ipo.id}><div><strong>{ipo.issuer_name}</strong><small>{ipo.issue_type === "SME" ? "SME" : "Mainboard"} · {ipo.status === "OPEN" && days >= 0 ? `Closes ${days === 0 ? "today" : `in ${days} days`}` : ipo.status} · {choice?.mode ? modeLabel(choice.mode) : "No mode selected"}</small></div><div className="home-ipo-end"><strong>{ipo.current_gmp_percent === null ? "GMP —" : `${ipo.current_gmp_percent}% GMP`}</strong><StatusBadge tone={choice?.selected ? "positive" : "neutral"}>{choice?.selected ? "Selected" : "Not selected"}</StatusBadge></div></li>; })}</ul>}
      </section>
      <section className="home-panel"><SectionHeading title="Action needed" detail="Items to review in this workspace" />
        {actions.length === 0 ? <EmptyState title="Nothing needs attention now." detail="New applications and upcoming dates will show here." /> : <ul className="action-list">{actions.slice(0, 8).map((action, index) => <li key={`${action.title}-${index}`}><div><strong>{action.title}</strong><small>{action.detail}</small></div><Link href={action.href} aria-label={`Review ${action.title}`}>Review →</Link></li>)}</ul>}
      </section>
    </div>
    <section className="home-panel" style={{ marginTop: 16 }}><SectionHeading title="Bank availability" detail="Money by account" action={<Link href="/funds">Manage funds →</Link>} />
      {(banks ?? []).length === 0 ? <EmptyState title="No bank accounts yet." detail="Add a bank and set its Balance to start planning." action={<Link href="/funds">Add bank</Link>} /> : <div className="compact-table-wrap"><table className="compact-table"><thead><tr><th>Bank</th><th>Balance</th><th>Blocked</th><th>Planned</th><th>Available</th></tr></thead><tbody>{(banks ?? []).map((bank) => { const line = capital?.by_bank?.[bank.id]; return <tr key={bank.id}><th scope="row">{bank.bank_name}<small>{bank.account_masked}</small></th><td>{formatInr(line?.balance ?? bank.current_balance)}</td><td>{line ? formatInr(line.blocked) : "—"}</td><td>{line ? formatInr(line.planned) : "—"}</td><td className="positive-cell">{line ? formatInr(line.available) : "—"}</td></tr>; })}</tbody></table></div>}
    </section>
  </div></main>;
}
