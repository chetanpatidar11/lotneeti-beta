"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { formatInr } from "@/lib/money";
import { Drawer } from "@/components/drawer";
import { EmptyState, MetricCard, PageHeader, SectionHeading, StatusBadge } from "@/components/ui";

export type AllottedApplication = {
  id: string;
  ipo_name: string;
  applicant_name: string;
  status: string;
  allotted_quantity: number | null;
};

export type SaleItem = {
  id: string;
  application: string;
  ipo_name: string;
  applicant_name: string;
  quantity: number;
  price_per_share: string;
  sold_on: string;
  charges: string;
  gross_proceeds: string;
  ipo_cost: string;
  realized_profit: string;
  roi_percent: string | null;
};

type ProfitTotals = {
  gross_proceeds: string;
  ipo_cost: string;
  charges: string;
  realized_profit: string;
  roi_percent: string | null;
};

export type ProfitReport = {
  sale_count: number;
  workspace: ProfitTotals;
  by_ipo: (ProfitTotals & { id: string; name: string })[];
  by_investor: (ProfitTotals & { id: string; name: string })[];
};

function ProfitLine({ label, totals }: { label: string; totals: ProfitTotals }) {
  return <div className="profit-line"><strong>{label}</strong><span>Sale amount {formatInr(totals.gross_proceeds)}</span><span>IPO cost {formatInr(totals.ipo_cost)}</span><span>Charges {formatInr(totals.charges)}</span><span>Realized profit {formatInr(totals.realized_profit)}</span><span>ROI {totals.roi_percent === null ? "—" : `${totals.roi_percent}%`}</span></div>;
}

function remaining(application: AllottedApplication, sales: SaleItem[]): number {
  return (application.allotted_quantity ?? 0) - sales.filter((sale) => sale.application === application.id).reduce((sum, sale) => sum + sale.quantity, 0);
}

export default function PortfolioScreen({ workspaceId, canEdit, initialApplications, initialSales, report, fromDate, toDate, initialLoadError = false }: {
  workspaceId: string;
  canEdit: boolean;
  initialApplications: AllottedApplication[];
  initialSales: SaleItem[];
  report: ProfitReport | null;
  fromDate: string;
  toDate: string;
  initialLoadError?: boolean;
}) {
  const router = useRouter();
  const [sales, setSales] = useState(initialSales);
  const [applicationId, setApplicationId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [soldOn, setSoldOn] = useState("");
  const [charges, setCharges] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saleFormOpen, setSaleFormOpen] = useState(false);
  const available = initialApplications.filter((item) => item.status === "ALLOTTED" && remaining(item, sales) > 0);
  const selected = available.find((item) => item.id === applicationId);

  function openSale(id = "") {
    setApplicationId(id);
    setSaleFormOpen(true);
    setError("");
  }

  async function record(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/sales`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ application: applicationId, quantity: Number(quantity), price_per_share: price, sold_on: soldOn, charges: charges || "0.00" }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error("We could not record this sale. Check the shares, price and charges.");
      setSales((current) => [result as SaleItem, ...current]);
      router.refresh();
      setSaleFormOpen(false);
      setApplicationId("");
      setQuantity("");
      setPrice("");
      setCharges("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not record this sale.");
    } finally {
      setBusy(false);
    }
  }

  if (initialLoadError) return <main className="page"><div className="shell portfolio-shell"><PageHeader eyebrow="Holdings & sales" title="Portfolio" /><div role="alert" className="plan-error">Portfolio data could not be loaded. <Link href="/portfolio">Retry</Link></div></div></main>;

  return <main className="page"><div className="shell portfolio-shell">
    <PageHeader eyebrow="Holdings & sales" title="Portfolio" description="Allotted shares and realized results." action={canEdit && available.length > 0 ? <button type="button" onClick={() => openSale()}>Record sale</button> : undefined} />
    {error && <div role="alert" className="plan-error">{error}</div>}
    {report ? <section className="metric-grid portfolio-metrics" aria-label="Realized profit summary">
      <MetricCard label="Realized Profit" value={formatInr(report.workspace.realized_profit)} tone="accent" note={`${report.sale_count} ${report.sale_count === 1 ? "sale" : "sales"} in period`} />
      <MetricCard label="Sale Proceeds" value={formatInr(report.workspace.gross_proceeds)} />
      <MetricCard label="Actual IPO Cost" value={formatInr(report.workspace.ipo_cost)} />
      <MetricCard label="Charges" value={formatInr(report.workspace.charges)} />
    </section> : <div role="alert" className="plan-error">Profit results could not be loaded. <Link href="/portfolio">Retry</Link></div>}
    <section className="section-panel portfolio-panel"><SectionHeading title="Allotted holdings" detail="Shares available to sell" action={<Link href="/applications">Applications →</Link>} />
      {available.length === 0 ? <EmptyState title="No allotted shares are awaiting sale." detail="Record an allotment result to see holdings here." /> : <div className="holding-list">{available.map((item) => <div className="holding-row" key={item.id}><div><strong>{item.ipo_name}</strong><small>{item.applicant_name}</small></div><span><StatusBadge tone="info">{remaining(item, sales)} shares left</StatusBadge></span>{canEdit && <button type="button" className="button-secondary" onClick={() => openSale(item.id)}>Sell shares</button>}</div>)}</div>}
    </section>
    <section className="section-panel portfolio-panel"><SectionHeading title="Realized results" detail="Grouped by IPO and investor" />
      <form method="get" action="/portfolio" className="profit-period"><label>From<input type="date" name="from_date" defaultValue={fromDate} /></label><label>To<input type="date" name="to_date" defaultValue={toDate} /></label><button type="submit">Show period</button><Link href="/portfolio">All dates</Link></form>
      {report && (report.by_ipo.length > 0 || report.by_investor.length > 0) ? <div className="profit-groups"><div><h3>By IPO</h3>{report.by_ipo.map((item) => <ProfitLine key={item.id} label={item.name} totals={item} />)}</div><div><h3>By investor</h3>{report.by_investor.map((item) => <ProfitLine key={item.id} label={item.name} totals={item} />)}</div></div> : <EmptyState title="No sales in this period." />}
    </section>
    <section className="section-panel portfolio-panel"><SectionHeading title="Recorded sales" detail="Exact cost and profit after each sale" />
      {sales.length === 0 ? <EmptyState title="No sales recorded yet." /> : <div className="compact-table-wrap"><table className="compact-table portfolio-sales-table"><thead><tr><th scope="col">IPO / investor</th><th scope="col">Sold</th><th scope="col">Proceeds</th><th scope="col">IPO cost</th><th scope="col">Charges</th><th scope="col">Profit / ROI</th></tr></thead><tbody>{sales.map((sale) => <tr key={sale.id}><th scope="row">{sale.ipo_name}<small>{sale.applicant_name} · {new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(`${sale.sold_on}T00:00:00Z`))}</small></th><td>{sale.quantity} shares</td><td>{formatInr(sale.gross_proceeds)}</td><td>{formatInr(sale.ipo_cost)}</td><td>{formatInr(sale.charges)}</td><td className="positive-cell">{formatInr(sale.realized_profit)}<small>{sale.roi_percent === null ? "ROI —" : `${sale.roi_percent}% ROI`}</small></td></tr>)}</tbody></table></div>}
    </section>
    {saleFormOpen && <Drawer title="Record sale" onClose={() => setSaleFormOpen(false)}><form className="sale-form sale-drawer-form" onSubmit={(event) => void record(event)}>
      {error && <p role="alert" className="plan-error">{error}</p>}
      <label>Allotted application<select required value={applicationId} onChange={(event) => setApplicationId(event.target.value)}><option value="">Choose application</option>{available.map((item) => <option key={item.id} value={item.id}>{item.ipo_name} · {item.applicant_name} · {remaining(item, sales)} shares left</option>)}</select></label>
      <label>Shares sold<input required type="number" min="1" max={selected ? remaining(selected, sales) : undefined} step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label>
      <label>Sale price per share (₹)<input required type="number" min="0.01" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} /></label>
      <label>Sale date<input required type="date" value={soldOn} onChange={(event) => setSoldOn(event.target.value)} /></label>
      <label>Charges (₹)<input type="number" min="0" step="0.01" value={charges} onChange={(event) => setCharges(event.target.value)} /></label>
      <p className="sale-preview-note">The recorded sale will show exact proceeds, allocated IPO cost, charges, profit and ROI.</p>
      <button type="submit" disabled={busy || !selected}>Record sale</button>
    </form></Drawer>}
  </div></main>;
}
