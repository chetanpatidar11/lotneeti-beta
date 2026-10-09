"use client";

import Link from "next/link";
import { useState } from "react";
import { applicationHistory, type ApplicationHistoryInput } from "@/lib/application-history";
import { formatInr } from "@/lib/money";
import { Drawer } from "@/components/drawer";
import { EmptyState, PageHeader, StatusBadge } from "@/components/ui";

export type ApplicationItem = ApplicationHistoryInput & {
  id: string;
  ipo_name: string;
  applicant_name: string;
  bank_label: string;
  upi_label: string;
  close_date: string;
  allotment_date: string;
  sold_quantity: number;
  category: string;
  lots: number;
  max_quantity: number;
};

function displayTime(value: string): string {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusLabel(status: ApplicationItem["status"]): string {
  return ({ PLANNED: "Planned", SUBMITTED: "Submitted", BLOCKED: "Blocked", ALLOTTED: "Allotted", NOT_ALLOTTED: "Not allotted" })[status];
}

function outcomeLabel(item: ApplicationItem): string {
  if (item.status !== "ALLOTTED" || item.sold_quantity === 0) return statusLabel(item.status);
  return item.sold_quantity >= (item.allotted_quantity ?? 0) ? "Sold" : "Partially sold";
}

function statusTone(item: ApplicationItem): "neutral" | "info" | "warning" | "positive" {
  if (item.status === "SUBMITTED") return "warning";
  if (item.status === "BLOCKED") return "info";
  if (item.status === "ALLOTTED") return "positive";
  return "neutral";
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function importantDate(item: ApplicationItem): { label: string; value: string } {
  if (item.status === "PLANNED" || item.status === "SUBMITTED") return { label: "Closes", value: dateLabel(item.close_date) };
  if (item.status === "BLOCKED") return { label: "Allotment", value: dateLabel(item.allotment_date) };
  return { label: "Result", value: item.result_at ? displayTime(item.result_at) : "—" };
}

function AllotmentForm({ item, busy, onSave }: { item: ApplicationItem; busy: boolean; onSave: (quantity: number, actualCost: string) => void }) {
  const [quantity, setQuantity] = useState("");
  const [actualCost, setActualCost] = useState("");
  return <form className="allotment-form" onSubmit={(event) => {
    event.preventDefault();
    onSave(Number(quantity), actualCost);
  }}>
    <label>Allotted shares<input type="number" min="1" max={item.max_quantity} step="1" required value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label>
    <label>Actual cost (₹)<input type="number" min="0.01" step="0.01" required value={actualCost} onChange={(event) => setActualCost(event.target.value)} /></label>
    <button type="submit" disabled={busy}>Mark Allotted</button>
  </form>;
}

export default function ApplicationsScreen({ workspaceId, canEdit, initialItems, latestRun, initialLoadError = false }: {
  workspaceId: string;
  canEdit: boolean;
  initialItems: ApplicationItem[];
  latestRun: { id: string | null; status: "READY" | "BLOCKED" | null };
  initialLoadError?: boolean;
}) {
  const [items, setItems] = useState(initialItems);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [resultId, setResultId] = useState<string | null>(null);
  const selectedItem = items.find((item) => item.id === selectedId);
  const resultItem = items.find((item) => item.id === resultId);

  async function startTracking() {
    if (!latestRun.id || latestRun.status !== "READY") return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/planner/runs/${latestRun.id}/track`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      const result = await response.json();
      if (!response.ok) throw new Error("We could not start tracking this plan.");
      setItems((current) => {
        const tracked = result as ApplicationItem[];
        const trackedIds = new Set(tracked.map((item) => item.id));
        return [...tracked, ...current.filter((item) => !trackedIds.has(item.id))];
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not start tracking this plan.");
    } finally {
      setBusy(false);
    }
  }

  async function update(item: ApplicationItem, action: "submit" | "block" | "not-allotted") {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/applications/${item.id}/${action}`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      const result = await response.json();
      if (!response.ok) throw new Error("We could not update this application.");
      setItems((current) => current.map((entry) => entry.id === item.id ? result as ApplicationItem : entry));
      setResultId(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not update this application.");
    } finally {
      setBusy(false);
    }
  }

  async function recordAllotment(item: ApplicationItem, quantity: number, actualCost: string) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/applications/${item.id}/allotted`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ quantity, actual_cost: actualCost }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error("We could not record this allotment. Check the quantity and actual cost.");
      setItems((current) => current.map((entry) => entry.id === item.id ? result as ApplicationItem : entry));
      setResultId(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not record this allotment.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="page"><div className="shell applications-shell">
    <PageHeader eyebrow="Execution" title="Applications" description="Track each application from plan to result." action={canEdit && latestRun.id ? <button type="button" disabled={busy || latestRun.status !== "READY"} onClick={() => void startTracking()}>Track latest plan</button> : undefined} />
    {error && <div className="plan-error" role="alert">{error} <button className="button-ghost" type="button" onClick={() => window.location.reload()}>Retry</button></div>}
    {initialLoadError ? <div className="plan-error" role="alert">Applications could not be loaded. <button className="button-ghost" type="button" onClick={() => window.location.reload()}>Retry</button></div> : items.length === 0 ? <EmptyState title="No applications are being tracked yet." detail="Save a ready plan, then track it here." action={<Link href="/plan">Review plan →</Link>} /> : <>
      <div className="application-summary" aria-label="Application status summary">
        <span><strong>{items.length}</strong> Total</span>
        <span><strong>{items.filter((item) => item.status === "PLANNED").length}</strong> To submit</span>
        <span><strong>{items.filter((item) => item.status === "SUBMITTED").length}</strong> Mandates pending</span>
        <span><strong>{items.filter((item) => item.status === "BLOCKED").length}</strong> Results pending</span>
      </div>
      <div className="application-table-wrap"><table className="application-table">
        <thead><tr><th scope="col">Applicant</th><th scope="col">IPO</th><th scope="col">Category</th><th scope="col">Amount</th><th scope="col">Bank / UPI</th><th scope="col">Status</th><th scope="col">Important date</th><th scope="col">Action</th></tr></thead>
        <tbody>{items.map((item) => { const date = importantDate(item); return <tr key={item.id}>
          <th scope="row" data-label="Applicant">{item.applicant_name}</th>
          <td data-label="IPO"><strong>{item.ipo_name}</strong><small>{item.lots} {item.lots === 1 ? "lot" : "lots"}</small></td>
          <td data-label="Category">{item.category === "SHNI" ? "sHNI" : "Retail"}</td>
          <td data-label="Amount" className="money-cell">{formatInr(item.amount)}</td>
          <td data-label="Bank / UPI">{item.bank_label}<small>{item.upi_label}</small></td>
          <td data-label="Status"><StatusBadge tone={statusTone(item)}>{outcomeLabel(item)}</StatusBadge></td>
          <td data-label="Important date"><small>{date.label}</small>{date.value}</td>
          <td data-label="Action"><div className="application-row-actions">
            {canEdit && item.status === "PLANNED" && <button type="button" disabled={busy} onClick={() => void update(item, "submit")}>Mark Submitted</button>}
            {canEdit && item.status === "SUBMITTED" && <button type="button" disabled={busy} onClick={() => void update(item, "block")}>Mark Blocked</button>}
            {canEdit && item.status === "BLOCKED" && <button type="button" disabled={busy} onClick={() => setResultId(item.id)}>Record Result</button>}
            {item.status === "ALLOTTED" && <Link className="button-secondary" href="/portfolio">View holding</Link>}
            <button type="button" className="button-ghost" onClick={() => setSelectedId(item.id)}>Details</button>
          </div></td>
        </tr>; })}</tbody>
      </table></div>
    </>}
    {selectedItem && <Drawer title={`${selectedItem.applicant_name} · ${selectedItem.ipo_name}`} onClose={() => setSelectedId(null)}>
      <div className="application-detail"><StatusBadge tone={statusTone(selectedItem)}>{outcomeLabel(selectedItem)}</StatusBadge><p>{selectedItem.category === "SHNI" ? "sHNI" : "Retail"} · {selectedItem.lots} {selectedItem.lots === 1 ? "lot" : "lots"} · {formatInr(selectedItem.amount)}</p><p>{selectedItem.bank_label} · {selectedItem.upi_label}</p></div>
      <h3>Progress</h3><ol className="application-timeline">{applicationHistory(selectedItem).map((event, index) => <li key={`${event.at}-${index}`}><time dateTime={event.at}>{displayTime(event.at)}</time><span>{event.label}</span></li>)}</ol>
      {selectedItem.status === "ALLOTTED" && <Link href="/portfolio">View holding →</Link>}
    </Drawer>}
    {resultItem && <Drawer title="Record application result" onClose={() => setResultId(null)}>
      <p className="intro">{resultItem.applicant_name} · {resultItem.ipo_name} · {formatInr(resultItem.amount)} blocked</p>
      <p>Recording the result releases the full application block. An allotment also deducts the actual cost from Balance.</p>
      <div className="result-options"><h3>Not allotted</h3><button className="button-secondary" type="button" disabled={busy} onClick={() => void update(resultItem, "not-allotted")}>Record not allotted</button></div>
      <div className="result-options"><h3>Allotted</h3><AllotmentForm item={resultItem} busy={busy} onSave={(quantity, actualCost) => void recordAllotment(resultItem, quantity, actualCost)} /></div>
    </Drawer>}
  </div></main>;
}
