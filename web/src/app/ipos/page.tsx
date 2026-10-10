import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import Link from "next/link";
import { backendUrl } from "@/lib/backend";
import { formatInr } from "@/lib/money";
import { amountForLots, minimumShniLots } from "@/lib/plan-amount";
import { selectedWorkspace } from "@/lib/workspace";
import { EmptyState, PageHeader, StatusBadge } from "@/components/ui";
import ThresholdSetting from "./threshold-setting";
import IPOChoice, { type IPOSelection } from "./ipo-choice";

type IPO = {
  id: string; issuer_name: string; symbol: string; issue_type: string; lower_price: string; upper_price: string;
  source_market: string; listing_exchanges: string; designated_exchange: string;
  lot_size: number; open_date: string; close_date: string; allotment_date: string; listing_date: string | null;
  status: string; current_gmp: string | null; current_gmp_percent: string | null; current_gmp_observed_at: string | null;
  gmp_source_count: number; gmp_source_conflict: boolean; gmp_stale_source_count: number;
  gmp_data_state: "FRESH" | "STALE" | "MISSING"; gmp_has_founder_correction: boolean;
};
type Observation = { id: string; value_per_share: string; source_value_per_share: string; percent: string; observed_at: string; source_key: string; enabled: boolean; fresh: boolean; included_in_consensus: boolean };
type Workspace = { id: string; role: string; auto_select_gmp_percent: string | null };
type Filter = "all" | "open" | "upcoming" | "closed" | "selected" | "skipped" | "mainboard" | "sme";
const filters: { id: Filter; label: string }[] = [
  { id: "all", label: "All" }, { id: "open", label: "Open" }, { id: "upcoming", label: "Upcoming" },
  { id: "closed", label: "Closed" },
  { id: "selected", label: "Selected" }, { id: "skipped", label: "Skipped" },
  { id: "mainboard", label: "Mainboard" }, { id: "sme", label: "SME" },
];
function dateLabel(value: string | null) {
  return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`)) : "—";
}
function observedLabel(value: string) {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata", timeZoneName: "short" }).format(new Date(value));
}
function Trend({ history }: { history: Observation[] }) {
  const points = [...history].reverse();
  if (points.length < 2) return null;
  const values = points.map((item) => Number(item.value_per_share));
  const low = Math.min(...values);
  const span = Math.max(...values) - low || 1;
  const coordinates = values.map((value, index) => `${10 + (index * 280) / (values.length - 1)},${35 - ((value - low) / span) * 27}`).join(" ");
  return <svg className="gmp-trend" viewBox="0 0 300 45" role="img" aria-label="GMP history trend"><polyline points={coordinates} fill="none" stroke="#49bd86" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
function matchFilter(ipo: IPO, choice: IPOSelection | undefined, filter: Filter) {
  if (filter === "open") return ipo.status === "OPEN";
  if (filter === "upcoming") return ipo.status === "UPCOMING";
  if (filter === "closed") return ["CLOSED", "ALLOTMENT", "LISTED"].includes(ipo.status);
  if (filter === "selected") return choice?.selected === true;
  if (filter === "skipped") return choice?.decision === "SKIP";
  if (filter === "mainboard") return ipo.issue_type === "MAINBOARD";
  if (filter === "sme") return ipo.issue_type === "SME";
  return true;
}

export default async function IPOsPage({ searchParams }: { searchParams: Promise<{ filter?: string; q?: string }> }) {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) redirect("/sign-in");
  const [workspaceResponse, response, params] = await Promise.all([
    fetch(backendUrl("workspaces/"), { headers: { cookie: cookieHeader }, cache: "no-store" }),
    fetch(backendUrl("ipos/"), { headers: { cookie: cookieHeader }, cache: "no-store" }),
    searchParams,
  ]);
  if (!response.ok || !workspaceResponse.ok) redirect("/sign-in");
  const ipos = (await response.json()) as IPO[];
  const workspace = await selectedWorkspace((await workspaceResponse.json()) as Workspace[]);
  let selections: IPOSelection[] = [];
  if (workspace) {
    const selectionResponse = await fetch(backendUrl(`workspaces/${workspace.id}/ipo-decisions/`), { headers: { cookie: cookieHeader }, cache: "no-store" });
    if (selectionResponse.ok) selections = (await selectionResponse.json()) as IPOSelection[];
  }
  const selectionMap = new Map(selections.map((selection) => [selection.ipo, selection]));
  const filter = filters.some((item) => item.id === params.filter) ? params.filter as Filter : "all";
  const q = (params.q ?? "").trim().toLocaleLowerCase("en-IN");
  const statusRank: Record<string, number> = { OPEN: 0, UPCOMING: 1, ALLOTMENT: 2, CLOSED: 3, LISTED: 4, CANCELLED: 5 };
  const visible = ipos.filter((ipo) => matchFilter(ipo, selectionMap.get(ipo.id), filter) && ipo.issuer_name.toLocaleLowerCase("en-IN").includes(q)).sort((a, b) => (statusRank[a.status] ?? 9) - (statusRank[b.status] ?? 9) || a.close_date.localeCompare(b.close_date) || a.issuer_name.localeCompare(b.issuer_name));
  const calendar = ipos.filter((ipo) => ["OPEN", "UPCOMING"].includes(ipo.status)).sort((a, b) => a.open_date.localeCompare(b.open_date)).slice(0, 8);
  const histories = await Promise.all(visible.map(async (ipo) => {
    try { const result = await fetch(backendUrl(`ipos/${ipo.id}/gmp-history/`), { headers: { cookie: cookieHeader }, cache: "no-store" }); return result.ok ? await result.json() as Observation[] : []; }
    catch { return [] as Observation[]; }
  }));
  return <main className="page"><div className="shell settings-shell">
    <PageHeader eyebrow="Market watch" title="IPOs" description="Review issue facts, GMP observations and your selection. GMP is not a guarantee." action={<Link className="button-link" href="/plan">Review plan →</Link>} />
    <div className="ipo-market-intro"><strong>InvestorGain market feed</strong><span>Issue dates and GMP can change. Review the latest details before applying.</span></div>
    {calendar.length > 0 && <section className="ipo-calendar" aria-label="Upcoming IPO dates"><div className="section-heading"><div><h2>IPO calendar</h2><p>Next open and upcoming issues</p></div></div><ul>{calendar.map((ipo) => <li key={ipo.id}><span className="ipo-calendar-date">{dateLabel(ipo.open_date)}</span><strong>{ipo.issuer_name}</strong><span>{ipo.issue_type === "SME" ? "SME" : "Mainboard"} · closes {dateLabel(ipo.close_date)}</span><StatusBadge tone={ipo.status === "OPEN" ? "positive" : "info"}>{ipo.status}</StatusBadge></li>)}</ul></section>}
    {workspace && <ThresholdSetting workspaceId={workspace.id} initialValue={workspace.auto_select_gmp_percent} canEdit={workspace.role === "OWNER"} />}
    <div className="filter-bar" role="group" aria-label="IPO filters">
      <form action="/ipos" method="get"><input type="search" name="q" aria-label="Search IPO issuer" placeholder="Search issuer" defaultValue={params.q ?? ""} /><input type="hidden" name="filter" value={filter} /><button type="submit" className="button-secondary">Search</button></form>
      {filters.map((item) => <Link className="filter-chip" key={item.id} href={`/ipos?filter=${item.id}${q ? `&q=${encodeURIComponent(params.q ?? "")}` : ""}`} aria-current={filter === item.id ? "true" : undefined}>{item.label}</Link>)}
      <span className="filter-count">{visible.length} of {ipos.length}</span>
    </div>
    {visible.length === 0 ? <EmptyState title={ipos.length === 0 ? "No InvestorGain IPOs are available yet." : "No IPOs match this view."} detail={ipos.length === 0 ? "Open and upcoming issues will appear after a successful market data sync." : "Try another filter or search term."} action={ipos.length > 0 ? <Link href="/ipos">Clear filters</Link> : undefined} /> : <div className="ipo-list">
      {visible.map((ipo, index) => {
        const selection = selectionMap.get(ipo.id);
        const history = histories[index].filter((item) => item.enabled);
        const trendHistory = history.filter((item) => item.source_key === history[0]?.source_key);
        const trend = trendHistory.length > 1 ? Number(trendHistory[0].value_per_share) - Number(trendHistory[1].value_per_share) : null;
        const shniLots = minimumShniLots(ipo.upper_price, ipo.lot_size);
        return <article className="ipo-card" key={ipo.id}>
          <div className="ipo-head"><div><div className="ipo-title-line"><h2>{ipo.issuer_name}</h2><StatusBadge tone="info">{ipo.issue_type === "SME" ? "SME" : "Mainboard"}</StatusBadge><StatusBadge tone="neutral">{ipo.listing_exchanges || "Exchange pending"}</StatusBadge><StatusBadge tone={ipo.status === "OPEN" ? "positive" : ipo.status === "UPCOMING" ? "info" : "neutral"}>{ipo.status}</StatusBadge></div><small>{ipo.symbol || "Public issue"}</small></div><div className="gmp-quote"><strong>{ipo.current_gmp === null ? ipo.gmp_data_state === "STALE" ? "GMP stale" : "GMP unavailable" : `${formatInr(ipo.current_gmp)} · ${ipo.current_gmp_percent}%`}</strong><small>{trend === null ? "No trend yet" : trend > 0 ? "↗ Rising observation" : trend < 0 ? "↘ Falling observation" : "→ Unchanged observation"}</small></div></div>
          <div className="ipo-facts">
            <div><span>Price band</span><strong>{formatInr(ipo.lower_price)} – {formatInr(ipo.upper_price)}</strong></div>
            <div><span>Lot size</span><strong>{ipo.lot_size} shares</strong></div>
            <div><span>Min retail</span><strong>{formatInr(amountForLots(ipo.upper_price, ipo.lot_size, 1))}</strong></div>
            <div><span>Min sHNI</span><strong>{shniLots} lots · {formatInr(amountForLots(ipo.upper_price, ipo.lot_size, shniLots))}</strong></div>
            <div><span>Open</span><strong>{dateLabel(ipo.open_date)}</strong></div>
            <div><span>Close</span><strong>{dateLabel(ipo.close_date)}</strong></div>
            <div><span>Allotment</span><strong>{dateLabel(ipo.allotment_date)}</strong></div>
          </div>
          <div className="ipo-controls"><div className="ipo-gmp-detail"><span className="detail-label">GMP observation</span><span>{ipo.current_gmp_observed_at ? observedLabel(ipo.current_gmp_observed_at) : "No fresh observation"} · {ipo.gmp_source_count} fresh {ipo.gmp_source_count === 1 ? "source" : "sources"}</span>{ipo.gmp_stale_source_count > 0 && <StatusBadge tone="warning">{ipo.gmp_stale_source_count} stale {ipo.gmp_stale_source_count === 1 ? "source" : "sources"}</StatusBadge>}{ipo.gmp_has_founder_correction && <StatusBadge tone="info">Founder corrected</StatusBadge>}<Trend history={trendHistory} />{history.length > 0 && <details className="sources-disclosure"><summary>GMP sources & history ({history.length})</summary><ol>{history.map((item) => <li key={item.id}>{observedLabel(item.observed_at)} · {formatInr(item.source_value_per_share)}{item.value_per_share !== item.source_value_per_share ? ` · corrected to ${formatInr(item.value_per_share)}` : ""}{!item.fresh ? " · stale" : item.included_in_consensus ? " · current source" : " · earlier observation"}</li>)}</ol></details>}</div>{workspace && <IPOChoice key={`${ipo.id}:${selection?.decision}:${selection?.selected}`} workspaceId={workspace.id} ipoId={ipo.id} initial={selection} canEdit={workspace.role !== "VIEWER"} />}</div>
        </article>;
      })}
    </div>}

  </div></main>;
}
