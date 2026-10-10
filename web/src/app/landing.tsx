import Link from "next/link";
import { backendUrl } from "@/lib/backend";
import { formatInr } from "@/lib/money";

type MarketIPO = {
  issuer_name: string; issue_type: string; status: string;
  lower_price: string; upper_price: string; lot_size: number;
  open_date: string; close_date: string; current_gmp: string | null;
  current_gmp_percent: string | null;
};
type MarketFeed = { issues: MarketIPO[]; last_success_at: string | null; status: string };

function dateLabel(value: string) {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

export default async function LandingPage() {
  let issues: MarketIPO[] = [];
  let lastSuccess: string | null = null;
  let sourceStatus = "NEVER";
  try {
    const response = await fetch(backendUrl("market/ipos/"), { cache: "no-store" });
    if (response.ok) {
      const feed = await response.json() as MarketFeed;
      issues = feed.issues;
      lastSuccess = feed.last_success_at;
      sourceStatus = feed.status;
    }
  } catch { /* The landing page remains usable while the feed is unavailable. */ }
  const featured = issues
    .filter((item) => item.status === "OPEN" || item.status === "UPCOMING")
    .sort((a, b) => Number(b.status === "OPEN") - Number(a.status === "OPEN") || a.open_date.localeCompare(b.open_date))
    .slice(0, 6);

  return <main className="landing-page">
    <header className="landing-nav"><Link href="/" className="landing-brand">Lot<span>Neeti</span><small>IPO PLANNING</small></Link><nav aria-label="Public navigation"><a href="#market">IPOs</a><a href="#how-it-works">How it works</a><Link className="landing-sign-in" href="/sign-in">Sign in</Link></nav></header>
    <section className="landing-hero"><div className="landing-hero-copy"><p className="landing-kicker">IPO planning for families and groups</p><h1>Every IPO decision, in one clear place.</h1><p>Explore current issues, plan across your family’s accounts, track applications and see what money is available.</p><div className="landing-actions"><Link className="button-link" href="/sign-in?mode=create">Create account</Link><a href="#market">Explore IPOs ↓</a></div><p className="landing-trust">No broker login needed. You review every application before you submit it.</p></div><div className="landing-hero-card" aria-label="LotNeeti planning steps"><span>01 · Discover</span><strong>See the issue details that matter</strong><span>02 · Plan</span><strong>Match applicants with available funds</strong><span>03 · Track</span><strong>Follow mandates, allotments and profit</strong></div></section>
    <section className="landing-market" id="market"><div className="landing-section-heading"><div><p className="landing-kicker">Market watch</p><h2>Open and upcoming IPOs</h2><p>InvestorGain issue data. GMP is an unofficial observation, never a guaranteed return.</p><p className="landing-source-time">{lastSuccess ? `Last synced ${new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(lastSuccess))} IST` : "Awaiting first successful source sync"}{sourceStatus === "ERROR" ? " · Latest update failed" : ""}</p></div><Link href="/sign-in">Plan with your accounts →</Link></div>
      {featured.length === 0 ? <div className="landing-empty">There are no complete open or upcoming issues in the latest saved feed. Please check back after the next sync.</div> : <div className="landing-ipo-grid">{featured.map((ipo) => <article key={`${ipo.issuer_name}-${ipo.open_date}`} className="landing-ipo-card"><div className="landing-ipo-top"><span>{ipo.issue_type === "SME" ? "SME" : "Mainboard"}</span><span className={ipo.status === "OPEN" ? "open" : "upcoming"}>{ipo.status === "OPEN" ? "Open now" : "Upcoming"}</span></div><h3>{ipo.issuer_name}</h3><dl><div><dt>Price</dt><dd>{formatInr(ipo.lower_price)}–{formatInr(ipo.upper_price)}</dd></div><div><dt>Lot</dt><dd>{ipo.lot_size} shares</dd></div><div><dt>Open · close</dt><dd>{dateLabel(ipo.open_date)} · {dateLabel(ipo.close_date)}</dd></div><div><dt>GMP</dt><dd>{ipo.current_gmp === null ? "Unavailable" : `${formatInr(ipo.current_gmp)} (${ipo.current_gmp_percent}%)`}</dd></div></dl></article>)}</div>}
    </section>
    <section className="landing-how" id="how-it-works"><p className="landing-kicker">Built for real IPO work</p><h2>From interest to outcome</h2><div className="landing-how-grid"><article><span>01</span><h3>Keep your accounts together</h3><p>Add family applicants, demat accounts, banks and UPI handles once.</p></article><article><span>02</span><h3>Review a practical plan</h3><p>See who can apply, which account can fund each application and why.</p></article><article><span>03</span><h3>Stay on top of results</h3><p>Track blocked funds, allotments, shares and recorded profit.</p></article></div><Link className="button-link" href="/sign-in?mode=create">Start with LotNeeti</Link></section>
    <footer className="landing-footer"><strong>LotNeeti</strong><span>Market data: InvestorGain. IPO and GMP information may change. Make your own investment decisions.</span><Link href="/sign-in">Sign in</Link></footer>
  </main>;
}
