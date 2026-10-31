"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Drawer } from "@/components/drawer";
import { EmptyState, MetricCard, PageHeader, SectionHeading, StatusBadge } from "@/components/ui";
import { filterGold, goldAmount, goldDate, goldError, goldForms, goldGrams, goldPriceLabel, goldTimestamp, unavailableGoldReport, type GoldPurchase, type GoldReport, type GoldSale } from "@/lib/gold";
import { indiaSaleDate } from "@/lib/sale-defaults";

type Editor = { kind: "purchase"; item?: GoldPurchase; requestId: string } | { kind: "sale"; purchase: GoldPurchase; item?: GoldSale; requestId: string };
type Removal = { kind: "purchase" | "sale"; item: GoldPurchase | GoldSale };
const amount = goldAmount;
const profitClass = (value: string | null) => value === null ? "" : Number(value) < 0 ? "gold-loss" : Number(value) > 0 ? "gold-profit" : "";

export default function GoldScreen({ workspaceId, canEdit, initialReport }: { workspaceId: string; canEdit: boolean; initialReport: GoldReport | null }) {
  const [report, setReport] = useState(initialReport);
  const [tab, setTab] = useState<"holdings" | "sales">("holdings");
  const [query, setQuery] = useState("");
  const [showRemoved, setShowRemoved] = useState(false);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [removal, setRemoval] = useState<Removal | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [priceMode, setPriceMode] = useState<"LIVE" | "MANUAL">("LIVE");
  const base = `/api/workspaces/${workspaceId}/gold/`;

  const change = useCallback(async function change(path: string, method: "GET" | "POST" | "PATCH" | "DELETE", body?: object, message = "Gold record saved.") {
    if (pending.current) return;
    pending.current = true;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(`${base}${path}`, {
        method, cache: "no-store",
        ...(body ? { headers: { "content-type": "application/json" }, body: JSON.stringify(body) } : {}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(goldError(result));
      setReport(result as GoldReport);
      if (method !== "GET") { setEditor(null); setRemoval(null); }
      setNotice(message);
    } catch (reason) {
      if (method === "GET") {
        setReport((current) => current ? unavailableGoldReport(current) : null);
        setError("Could not refresh prices. Your saved records are unchanged. Please try again.");
      } else setError(reason instanceof Error ? reason.message : "Unable to save. Please try again.");
    }
    finally { pending.current = false; setBusy(false); }
  }, [base]);
  useEffect(() => {
    const refresh = () => {
      if (!document.hidden && !pending.current && !editor && !removal) void change("", "GET", undefined, "");
    };
    const timer = window.setInterval(refresh, 60_000);
    document.addEventListener("visibilitychange", refresh);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", refresh); };
  }, [change, editor, removal]);
  function openPurchase(item?: GoldPurchase) { setPriceMode(item?.price_mode ?? "LIVE"); setError(""); setNotice(""); setEditor({ kind: "purchase", item, requestId: crypto.randomUUID() }); }
  function openSale(purchase: GoldPurchase, item?: GoldSale) { setError(""); setNotice(""); setEditor({ kind: "sale", purchase, item, requestId: crypto.randomUUID() }); }
  function close() { if (!pending.current) { setEditor(null); setRemoval(null); setError(""); } }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor) return;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    if (editor.kind === "purchase") {
      void change(editor.item ? `purchases/${editor.item.id}/` : "", editor.item ? "PATCH" : "POST", {
        ...data, current_price_per_gram: priceMode === "LIVE" ? editor.item?.current_price_per_gram ?? null : data.current_price_per_gram || null,
        ...(!editor.item ? { request_id: editor.requestId } : {}),
      }, editor.item ? "Purchase updated." : "Purchase added.");
    } else {
      void change(editor.item ? `sales/${editor.item.id}/` : "sales/", editor.item ? "PATCH" : "POST", {
        ...data, ...(!editor.item ? { purchase: editor.purchase.id, request_id: editor.requestId } : {}),
      }, editor.item ? "Sale updated." : "Sale recorded.");
    }
  }
  function recordPath(kind: "purchase" | "sale", id: string) { return `${kind === "purchase" ? "purchases" : "sales"}/${id}/`; }
  function actions(kind: "purchase" | "sale", item: GoldPurchase | GoldSale) {
    if (!canEdit) return null;
    if (item.removed) return <button className="button-secondary" disabled={busy} onClick={() => void change(recordPath(kind, item.id), "POST", {}, "Record restored.")}>Restore</button>;
    return <>
      <button className="button-secondary" disabled={busy} onClick={() => {
        if (kind === "purchase") openPurchase(item as GoldPurchase);
        else { const purchase = report?.purchases.find((purchase) => purchase.id === (item as GoldSale).purchase); if (purchase) openSale(purchase, item as GoldSale); }
      }}>Edit</button>
      {kind === "purchase" && Number((item as GoldPurchase).remaining_grams) > 0 && <button className="button-secondary" disabled={busy} onClick={() => openSale(item as GoldPurchase)}>Sell</button>}
      <button className="button-ghost" disabled={busy} onClick={() => { setError(""); setRemoval({ kind, item }); }}>Remove</button>
    </>;
  }
  const summary = report?.summary;
  const purchases = filterGold(report?.purchases ?? [], query, showRemoved);
  const sales = filterGold(report?.sales ?? [], query, showRemoved);
  const activeSales = report?.sales.filter((sale) => !sale.removed).length ?? 0;

  return <main className="page gold-page">
    <PageHeader eyebrow="PHYSICAL GOLD" title="Gold" description="Your coins, bars and jewellery, in one place." action={canEdit && report && <button disabled={busy} onClick={() => openPurchase()}>+ Add purchase</button>} />
    {!report ? <EmptyState title="Gold records could not be loaded." detail="Try again to see your saved purchases and sales." action={<button disabled={busy} onClick={() => void change("", "GET", undefined, "Gold records refreshed.")}>{busy ? "Loading…" : "Try again"}</button>} /> : <>
      <section className="gold-market" aria-label="Gold market prices">
        <div className="gold-market-heading"><strong>{report.market.state === "LIVE" ? "Live gold prices" : report.market.state === "STALE" ? "Last available gold prices" : "Live gold prices unavailable"}</strong><a href="https://gold-api.com/" target="_blank" rel="noreferrer">Gold API ↗</a><button className="button-secondary" disabled={busy || !!editor || !!removal} onClick={() => void change("", "GET", undefined, "Prices refreshed.")}>{busy ? "Updating…" : "Refresh prices"}</button></div>
        {Object.keys(report.market.rates).length > 0 && <div className="gold-market-rates">{[["999", "24K / 999"], ["916", "22K / 916"], ["750", "18K / 750"]].map(([fine, label]) => <span key={fine}>{label} <strong>{amount(report.market.rates[fine] ?? null)}<small> / g</small></strong></span>)}</div>}
        <p>{report.market.as_of ? <><span>{report.market.state === "STALE" ? "Using an older quote. " : "Updated "}</span><time dateTime={report.market.as_of}>{goldTimestamp(report.market.as_of)}</time> · </> : "Your purchases and sales are still available. "}Spot estimate in INR, adjusted for purity. Local taxes, making charges and dealer premiums are excluded. Updates every minute.</p>
      </section>
      <div className="gold-metrics">
        <MetricCard label="Gold held" value={<>{goldGrams(summary!.grams_held)} <span className="gold-unit">g</span></>} note={`${summary!.purchase_count} purchase${summary!.purchase_count === 1 ? "" : "s"} recorded`} tone="accent" />
        <MetricCard label="Cost of holdings" value={amount(summary!.cost_of_holdings)} note="Cost of gold you still hold" />
        <MetricCard label="Estimated value" value={amount(summary!.estimated_value)} note={summary!.unpriced_holdings ? `${summary!.unpriced_holdings} holding${summary!.unpriced_holdings === 1 ? " needs" : "s need"} a current price` : "Using market prices or your manual quotes"} />
        <MetricCard label="Unrealized profit / loss" value={<span className={profitClass(summary!.unrealized_profit)}>{amount(summary!.unrealized_profit)}</span>} note="Estimated value less remaining cost" />
      </div>
      <div className="gold-summary-line"><span>Total paid <strong>{amount(summary!.total_paid)}</strong></span><span>Net sale receipts <strong>{amount(summary!.net_sale_receipts)}</strong></span><span>Realized profit / loss <strong className={profitClass(summary!.realized_profit)}>{amount(summary!.realized_profit)}</strong></span></div>
      <section className="section-panel gold-panel">
        <div className="gold-toolbar">
          <div className="gold-tabs" role="tablist" aria-label="Gold records">{(["holdings", "sales"] as const).map((item) => <button key={item} role="tab" aria-selected={tab === item} aria-controls={`gold-${item}`} id={`gold-tab-${item}`} onClick={() => setTab(item)}>{item === "holdings" ? "Holdings" : "Sales"}<span>{item === "holdings" ? summary!.purchase_count : activeSales}</span></button>)}</div>
          <label className="gold-search">Search records<input type="search" placeholder="Name, owner or purity" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <label className="gold-removed-toggle"><input type="checkbox" checked={showRemoved} onChange={(event) => setShowRemoved(event.target.checked)} />Show removed</label>
        </div>
        <div role="tabpanel" id={`gold-${tab}`} aria-labelledby={`gold-tab-${tab}`} tabIndex={0}>
          {tab === "holdings" ? <>
            <SectionHeading title="Your gold" detail="Live prices follow each item’s purity. Choose a manual resale quote using Edit." />
            {purchases.length === 0 ? <EmptyState title={report.purchases.length ? "No matching purchases." : "Add your first gold purchase."} detail="Track the net gold weight and total invoice cost, including making charges and taxes." /> : <div className="gold-table-wrap"><table className="gold-table"><caption className="visually-hidden">Physical gold holdings</caption><thead><tr><th>Purchased</th><th>Gold / owner</th><th>Purity</th><th className="gold-number">Held (g)</th><th className="gold-number">Cost held</th><th className="gold-number">Price / g</th><th className="gold-number">Est. value</th><th className="gold-number">Profit / loss</th><th>Status</th>{canEdit && <th>Actions</th>}</tr></thead><tbody>{purchases.map((item) => <tr key={item.id} className={item.removed ? "gold-row-removed" : undefined}>
              <td><time dateTime={item.purchased_on}>{goldDate(item.purchased_on)}</time></td>
              <td><span className="gold-item-name">{item.name}</span>{item.owner_name && <span className="gold-inline-owner"> · {item.owner_name}</span>}<span className="visually-hidden"> {goldForms[item.form]}</span></td><td>{item.purity}</td>
              <td className="gold-number" title={`Purchased ${goldGrams(item.grams)} g · Sold ${goldGrams(item.sold_grams)} g`}>{goldGrams(item.remaining_grams)}</td><td className="gold-number">{amount(item.remaining_cost)}</td>
              <td className="gold-number" title={item.price_as_of ? `${goldPriceLabel(item.price_source)} · ${goldTimestamp(item.price_as_of)}` : "Edit purity or use a manual resale quote"}>{amount(item.effective_price_per_gram)}<span className="gold-price-source">{goldPriceLabel(item.price_source)}</span></td>
              <td className="gold-number">{amount(item.estimated_value)}</td><td className={`gold-number ${profitClass(item.unrealized_profit)}`}>{amount(item.unrealized_profit)}</td>
              <td><StatusBadge tone={item.removed ? "neutral" : Number(item.remaining_grams) === 0 ? "positive" : item.effective_price_per_gram === null || item.price_source === "STALE" ? "warning" : "info"}>{item.removed ? "Removed" : Number(item.remaining_grams) === 0 ? "Sold" : item.price_source === "UNKNOWN_PURITY" ? "Set purity" : item.effective_price_per_gram === null ? "Add price" : "Held"}</StatusBadge></td>
              {canEdit && <td><div className="gold-actions">{actions("purchase", item)}</div></td>}
            </tr>)}</tbody></table></div>}
          </> : <>
            <SectionHeading title="Recorded sales" detail="Profit uses the purchase cost of the gold sold and the net amount received." />
            {sales.length === 0 ? <EmptyState title="No matching sales." detail="Choose Sell beside a holding to record a full or partial sale." /> : <div className="gold-table-wrap"><table className="gold-table"><caption className="visually-hidden">Physical gold sales</caption><thead><tr><th>Sold</th><th>Gold / owner</th><th>Purity</th><th className="gold-number">Sold (g)</th><th className="gold-number">Net received</th><th className="gold-number">Purchase cost</th><th className="gold-number">Profit / loss</th><th>Status</th>{canEdit && <th>Actions</th>}</tr></thead><tbody>{sales.map((item) => <tr key={item.id} className={item.removed ? "gold-row-removed" : undefined}>
              <td><time dateTime={item.sold_on}>{goldDate(item.sold_on)}</time></td><td><strong>{item.name}</strong>{item.owner_name && <span className="gold-inline-owner"> · {item.owner_name}</span>}</td><td>{item.purity}</td><td className="gold-number">{goldGrams(item.grams)}</td><td className="gold-number">{amount(item.net_proceeds)}</td><td className="gold-number">{amount(item.allocated_cost)}</td><td className={`gold-number ${profitClass(item.realized_profit)}`}>{amount(item.realized_profit)}</td><td><StatusBadge tone={item.removed ? "neutral" : "positive"}>{item.removed ? "Removed" : "Recorded"}</StatusBadge></td>{canEdit && <td><div className="gold-actions">{actions("sale", item)}</div></td>}
            </tr>)}</tbody></table></div>}
          </>}
        </div>
      </section>
      <p className="gold-footnote">Weights are net gold grams at each item’s stated purity. Estimates use live spot prices or your manual quotes; your jeweller’s buying price may differ. Gold purchases and sales do not change your IPO bank balances.</p>
    </>}
    {notice && <p role="status" className="notice">{notice}</p>}
    {error && !editor && !removal && <p role="alert" className="error">{error}</p>}
    {editor && <Drawer title={editor.kind === "purchase" ? editor.item ? "Edit gold purchase" : "Add gold purchase" : editor.item ? "Edit gold sale" : "Record gold sale"} onClose={close} canClose={!busy}>
      <form className="gold-form" onSubmit={submit}>
        <fieldset disabled={busy}>
          {editor.kind === "purchase" ? <>
            <label>Name<input name="name" required maxLength={120} defaultValue={editor.item?.name} placeholder="e.g. Gold coin" /></label>
            <div className="gold-form-pair"><label>Form<select name="form" defaultValue={editor.item?.form ?? "COIN"}>{Object.entries(goldForms).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Purity<input name="purity" list="gold-purities" required maxLength={20} defaultValue={editor.item?.purity ?? "24K / 999"} /><datalist id="gold-purities"><option value="24K / 999" /><option value="22K / 916" /><option value="18K / 750" /></datalist></label></div>
            <label>Owner <span className="gold-optional">(optional)</span><input name="owner_name" maxLength={120} defaultValue={editor.item?.owner_name} /></label>
            <label>Purchase date<input type="date" name="purchased_on" required max={indiaSaleDate()} defaultValue={editor.item?.purchased_on ?? indiaSaleDate()} /></label>
            <label>Net gold weight (g)<input type="number" inputMode="decimal" name="grams" required min="0.000001" max="99999999.999999" step="0.000001" defaultValue={editor.item?.grams} /><small>Use the gold weight only, excluding stones.</small></label>
            <label>Total paid (₹)<input type="number" inputMode="decimal" name="total_cost" required min="0.01" max="99999999999999.99" step="0.01" defaultValue={editor.item?.total_cost} /><small>Include making charges, taxes and other purchase charges.</small></label>
            <label>Valuation price<select name="price_mode" value={priceMode} onChange={(event) => setPriceMode(event.target.value as "LIVE" | "MANUAL")}><option value="LIVE">Live market price (automatic)</option><option value="MANUAL">My resale quote (manual)</option></select></label>
            <label hidden={priceMode === "LIVE"}>My resale price / g (₹) <span className="gold-optional">(optional)</span><input type="number" inputMode="decimal" name="current_price_per_gram" disabled={priceMode === "LIVE"} min="0.01" max="9999999999.99" step="0.01" defaultValue={editor.item?.current_price_per_gram ?? ""} /><small>{priceMode === "LIVE" ? "Saved for your reference. The live market price is used while automatic is selected." : "Enter a quote for this purity. It stays unchanged until you edit it."}</small></label>
            <label>Seller <span className="gold-optional">(optional)</span><input name="seller" maxLength={120} defaultValue={editor.item?.seller} /></label>
            {editor.item && Number(editor.item.sold_grams) > 0 && <p className="gold-form-note">{goldGrams(editor.item.sold_grams)} g already sold. Editing the purchase cost also updates the profit on those sales.</p>}
          </> : <>
            <div className="gold-form-note"><strong>{editor.purchase.name}</strong><p>{editor.purchase.purity} · {goldGrams(editor.purchase.remaining_grams)} g remaining</p></div>
            <label>Sale date<input type="date" name="sold_on" required min={editor.purchase.purchased_on} max={indiaSaleDate()} defaultValue={editor.item?.sold_on ?? indiaSaleDate()} /></label>
            <label>Gold sold (g)<input type="number" inputMode="decimal" name="grams" required min="0.000001" step="0.000001" defaultValue={editor.item?.grams ?? editor.purchase.remaining_grams} /><small>You can record a full or partial sale.</small></label>
            <label>Net amount received (₹)<input type="number" inputMode="decimal" name="net_proceeds" required min="0.01" max="99999999999999.99" step="0.01" defaultValue={editor.item?.net_proceeds} /><small>Enter the amount after all sale charges and deductions.</small></label>
          </>}
          <label>Notes <span className="gold-optional">(optional)</span><textarea name="notes" rows={3} maxLength={500} defaultValue={editor.item?.notes} /></label>
        </fieldset>
        {error && <p role="alert" className="error">{error}</p>}
        <div className="gold-form-buttons"><button type="button" className="button-secondary" disabled={busy} onClick={close}>Cancel</button><button type="submit" disabled={busy}>{busy ? "Saving…" : editor.kind === "purchase" ? "Save purchase" : "Save sale"}</button></div>
      </form>
    </Drawer>}
    {removal && <Drawer title={`Remove ${removal.kind}?`} onClose={close} canClose={!busy}><p>Remove “{removal.item.name}” from your gold totals? You can restore it using Show removed.</p>{removal.kind === "purchase" && <p>Any recorded sales must be removed first.</p>}{error && <p role="alert" className="error">{error}</p>}<div className="gold-form-buttons"><button className="button-secondary" disabled={busy} onClick={close}>Keep record</button><button disabled={busy} onClick={() => void change(recordPath(removal.kind, removal.item.id), "DELETE", undefined, "Record removed. You can restore it using Show removed.")}>{busy ? "Removing…" : "Remove record"}</button></div></Drawer>}
  </main>;
}
