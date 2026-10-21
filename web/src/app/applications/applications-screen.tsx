"use client";

import Link from "next/link";
import { useState } from "react";
import { applicationHistory, type ApplicationHistoryInput } from "@/lib/application-history";
import { formatInr } from "@/lib/money";
import { Drawer } from "@/components/drawer";
import { ConfirmationDialog } from "@/components/confirmation-dialog";
import { EmptyState, PageHeader, StatusBadge } from "@/components/ui";

export type ApplicationItem = ApplicationHistoryInput & {
  id: string;
  ipo: string;
  ipo_name: string;
  applicant_name: string;
  bank: string;
  bank_label: string;
  upi: string;
  upi_label: string;
  close_date: string;
  allotment_date: string;
  sold_quantity: number;
  category: string;
  lots: number;
  max_quantity: number;
  edited_at: string | null;
  cancelled_at: string | null;
};

type BankOption = { id: string; bank_name: string; account_display: string; active: boolean; is_placeholder: boolean };
type UpiOption = { id: string; bank: string; handle: string; active: boolean; verified: boolean };
type BulkAction = "submit" | "block" | "not-allotted" | "cancel";
type Filter = "ACTIVE" | "ALL" | "PLANNED" | "SUBMITTED" | "BLOCKED" | "RESULTS" | "CANCELLED";

function displayTime(value: string): string {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusLabel(status: ApplicationItem["status"]): string {
  return ({ PLANNED: "Planned", SUBMITTED: "Submitted", BLOCKED: "Blocked", ALLOTTED: "Allotted", NOT_ALLOTTED: "Not allotted", CANCELLED: "Cancelled" })[status];
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
  if (item.status === "CANCELLED") return { label: "Cancelled", value: item.cancelled_at ? displayTime(item.cancelled_at) : "—" };
  if (item.status === "PLANNED" || item.status === "SUBMITTED") return { label: "Closes", value: dateLabel(item.close_date) };
  if (item.status === "BLOCKED") return { label: "Allotment", value: dateLabel(item.allotment_date) };
  return { label: "Result", value: item.result_at ? displayTime(item.result_at) : "—" };
}

function canCancel(item: ApplicationItem): boolean {
  return ["PLANNED", "SUBMITTED", "BLOCKED"].includes(item.status);
}

function filterMatches(item: ApplicationItem, filter: Filter): boolean {
  if (filter === "ALL") return true;
  if (filter === "ACTIVE") return canCancel(item);
  if (filter === "RESULTS") return item.status === "ALLOTTED" || item.status === "NOT_ALLOTTED";
  return item.status === filter;
}

async function responseError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null) as { detail?: unknown; message?: unknown } | null;
  return typeof body?.detail === "string" ? body.detail : typeof body?.message === "string" ? body.message : fallback;
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
  const [editError, setEditError] = useState("");
  const [resultError, setResultError] = useState("");
  const [message, setMessage] = useState("");
  const [filter, setFilter] = useState<Filter>("ACTIVE");
  const [ipoFilter, setIpoFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [pendingCancelIds, setPendingCancelIds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [resultId, setResultId] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [banks, setBanks] = useState<BankOption[]>([]);
  const [upis, setUpis] = useState<UpiOption[]>([]);
  const [editCategory, setEditCategory] = useState("RETAIL");
  const [editLots, setEditLots] = useState(1);
  const [editBank, setEditBank] = useState("");
  const [editUpi, setEditUpi] = useState("");
  const selectedItem = items.find((item) => item.id === selectedId);
  const resultItem = items.find((item) => item.id === resultId);
  const editItem = items.find((item) => item.id === editId);
  const selectedItems = items.filter((item) => selectedIds.includes(item.id));
  const ipoOptions = [...new Map(items.map((item) => [item.ipo, { name: item.ipo_name, closeDate: item.close_date }])).entries()]
    .sort((left, right) => right[1].closeDate.localeCompare(left[1].closeDate) || left[1].name.localeCompare(right[1].name));
  const ipoItems = items.filter((item) => item.ipo === ipoFilter);
  const visible = ipoItems.filter((item) => filterMatches(item, filter) && `${item.applicant_name} ${item.upi_label}`.toLowerCase().includes(search.toLowerCase().trim()));
  const groups = Object.entries(visible.reduce<Record<string, ApplicationItem[]>>((current, item) => {
    (current[item.ipo] ??= []).push(item);
    return current;
  }, {}));
  const eligibleUpis = upis.filter((upi) => upi.bank === editBank && upi.active && upi.verified);

  function replaceItems(changed: ApplicationItem[]) {
    const byId = new Map(changed.map((item) => [item.id, item]));
    setItems((current) => current.map((item) => byId.get(item.id) ?? item));
  }

  function toggleSelection(ids: string[], checked: boolean) {
    setSelectedIds((current) => checked ? [...new Set([...current, ...ids])] : current.filter((id) => !ids.includes(id)));
  }

  async function startTracking() {
    if (!latestRun.id || latestRun.status !== "READY") return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/planner/runs/${latestRun.id}/track`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      const result = await response.json();
      if (!response.ok) throw new Error(await responseError(response, "We could not start tracking this plan."));
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
    setResultError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/applications/${item.id}/${action}`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      if (!response.ok) throw new Error(await responseError(response, "We could not update this application."));
      replaceItems([await response.json() as ApplicationItem]);
      setResultId(null);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "We could not update this application.";
      if (resultId) setResultError(message);
      else setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function bulkUpdate(action: BulkAction, ids: string[]) {
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/applications/bulk`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action, ids }) });
      if (!response.ok) throw new Error(await responseError(response, "No applications were changed. Review the selection and try again."));
      replaceItems(await response.json() as ApplicationItem[]);
      setSelectedIds([]);
      setPendingCancelIds([]);
      setMessage(`${ids.length} ${ids.length === 1 ? "application" : "applications"} ${action === "cancel" ? "cancelled" : "updated"}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No applications were changed.");
      setPendingCancelIds([]);
    } finally { setBusy(false); }
  }

  async function openEdit(item: ApplicationItem) {
    setEditId(item.id);
    setEditCategory(item.category);
    setEditLots(item.lots);
    setEditBank(item.bank);
    setEditUpi(item.upi);
    setEditLoading(true);
    setError("");
    setEditError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/banks`);
      if (!response.ok) throw new Error("Bank accounts could not be loaded.");
      const loadedBanks = await response.json() as BankOption[];
      const upiResponses = await Promise.all(loadedBanks.map(async (bank) => {
        const result = await fetch(`/api/workspaces/${workspaceId}/banks/${bank.id}/upis`);
        if (!result.ok) throw new Error("UPI accounts could not be loaded.");
        return (await result.json() as Omit<UpiOption, "bank">[]).map((upi) => ({ ...upi, bank: bank.id }));
      }));
      setBanks(loadedBanks);
      setUpis(upiResponses.flat());
    } catch (caught) { setEditError(caught instanceof Error ? caught.message : "Account choices could not be loaded."); }
    finally { setEditLoading(false); }
  }

  async function saveEdit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editItem) return;
    setBusy(true); setEditError(""); setMessage("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/applications/${editItem.id}/edit`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ category: editCategory, lots: editLots, bank: editBank, upi: editUpi }) });
      if (!response.ok) throw new Error(await responseError(response, "We could not save this application."));
      replaceItems([await response.json() as ApplicationItem]);
      setEditId(null);
      setMessage("Application details updated.");
    } catch (caught) { setEditError(caught instanceof Error ? caught.message : "We could not save this application."); }
    finally { setBusy(false); }
  }

  async function recordAllotment(item: ApplicationItem, quantity: number, actualCost: string) {
    setBusy(true);
    setResultError("");
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
      setResultError(caught instanceof Error ? caught.message : "We could not record this allotment.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="page"><div className="shell applications-shell">
    <PageHeader eyebrow="Execution" title="Applications" description="Manage applications by IPO, then track submission and results." action={canEdit && latestRun.id ? <button type="button" disabled={busy || latestRun.status !== "READY"} onClick={() => void startTracking()}>Track latest plan</button> : undefined} />
    {error && <div className="plan-error" role="alert">{error}</div>}
    {message && <p className="plan-success" role="status">{message}</p>}
    {initialLoadError ? <div className="plan-error" role="alert">Applications could not be loaded. <button className="button-ghost" type="button" onClick={() => window.location.reload()}>Retry</button></div> : items.length === 0 ? <EmptyState title="No applications are being tracked yet." detail="Save a ready plan, then track it here." action={<Link href="/plan">Review plan →</Link>} /> : <>
      <section className="application-ipo-picker" aria-label="Choose an IPO to view applications">
        <div><span className="application-picker-eyebrow">Your applications</span><label htmlFor="application-ipo-choice">Choose an IPO</label><p>Select one IPO to review its applications and update their progress.</p></div>
        <select id="application-ipo-choice" value={ipoFilter} onChange={(event) => { setIpoFilter(event.target.value); setSearch(""); setFilter("ACTIVE"); setSelectedIds([]); }}><option value="">Select an IPO</option>{ipoOptions.map(([id, option]) => <option key={id} value={id}>{option.name} · closes {dateLabel(option.closeDate)}</option>)}</select>
      </section>
      {!ipoFilter && <EmptyState title="Choose an IPO to see its applications." detail="Each IPO has its own application list and bulk actions." />}
      {ipoFilter && <>
      <div className="application-summary" aria-label="Application status summary for selected IPO">
        <span><strong>{ipoItems.filter(canCancel).length}</strong> Active</span>
        <span><strong>{ipoItems.filter((item) => item.status === "PLANNED").length}</strong> To submit</span>
        <span><strong>{ipoItems.filter((item) => item.status === "SUBMITTED").length}</strong> Mandates pending</span>
        <span><strong>{ipoItems.filter((item) => item.status === "BLOCKED").length}</strong> Results pending</span>
        <span><strong>{ipoItems.filter((item) => item.status === "CANCELLED").length}</strong> Cancelled</span>
      </div>
      <div className="application-filters">
        <label>Search<input type="search" value={search} onChange={(event) => { setSearch(event.target.value); setSelectedIds([]); }} placeholder="Applicant or UPI" /></label>
        <label>Status<select value={filter} onChange={(event) => { setFilter(event.target.value as Filter); setSelectedIds([]); }}><option value="ACTIVE">Active</option><option value="ALL">All</option><option value="PLANNED">Planned</option><option value="SUBMITTED">Submitted</option><option value="BLOCKED">Blocked</option><option value="RESULTS">Results</option><option value="CANCELLED">Cancelled</option></select></label>
      </div>
      {canEdit && selectedItems.length > 0 && <div className="application-bulk" role="group" aria-label="Selected application actions"><strong>{selectedItems.length} selected</strong><button type="button" className="button-secondary" disabled={busy || !selectedItems.every((item) => item.status === "PLANNED")} onClick={() => void bulkUpdate("submit", selectedIds)}>Mark submitted</button><button type="button" className="button-secondary" disabled={busy || !selectedItems.every((item) => item.status === "SUBMITTED")} onClick={() => void bulkUpdate("block", selectedIds)}>Mark blocked</button><button type="button" className="button-secondary" disabled={busy || !selectedItems.every((item) => item.status === "BLOCKED")} onClick={() => void bulkUpdate("not-allotted", selectedIds)}>Not allotted</button><button type="button" className="button-danger" disabled={busy || !selectedItems.every(canCancel)} onClick={() => setPendingCancelIds(selectedIds)}>Cancel selected</button><button type="button" className="button-ghost" onClick={() => setSelectedIds([])}>Clear</button></div>}
      {groups.length === 0 ? <EmptyState title="No applications match these filters." detail="Try a different IPO, status or search." /> : groups.map(([ipoId, group]) => {
        const eligibleIds = group.filter(canCancel).map((item) => item.id);
        return <section className="application-ipo-group" key={ipoId} aria-label={`${group[0].ipo_name} applications`}>
          <header className="application-ipo-heading"><div><h2>{group[0].ipo_name}</h2><p>{group.length} {group.length === 1 ? "application" : "applications"} · Closes {dateLabel(group[0].close_date)}</p></div>{canEdit && eligibleIds.length > 0 && <label className="application-select-group application-select-mobile"><input type="checkbox" checked={eligibleIds.every((id) => selectedIds.includes(id))} onChange={(event) => toggleSelection(eligibleIds, event.target.checked)} disabled={busy} /> Select all</label>}</header>
          <div className="application-table-wrap"><table className="application-table"><thead><tr>{canEdit && <th scope="col" className="application-select-heading"><label className="application-select-group"><input type="checkbox" aria-label="Select all visible applications" checked={eligibleIds.length > 0 && eligibleIds.every((id) => selectedIds.includes(id))} onChange={(event) => toggleSelection(eligibleIds, event.target.checked)} disabled={busy || eligibleIds.length === 0} /> Select all</label></th>}<th scope="col">Applicant</th><th scope="col">Category</th><th scope="col">Amount</th><th scope="col">Bank / UPI</th><th scope="col">Status</th><th scope="col">Important date</th><th scope="col">Actions</th></tr></thead><tbody>{group.map((item) => { const date = importantDate(item); return <tr key={item.id}>
            {canEdit && <td data-label="Select" className="application-select-cell">{canCancel(item) && <input type="checkbox" aria-label={`Select ${item.applicant_name} for ${item.ipo_name}`} checked={selectedIds.includes(item.id)} disabled={busy} onChange={(event) => toggleSelection([item.id], event.target.checked)} />}</td>}
            <th scope="row" data-label="Applicant">{item.applicant_name}</th>
            <td data-label="Category">{item.category === "SHNI" ? "sHNI" : "Retail"}<small>{item.lots} {item.lots === 1 ? "lot" : "lots"}</small></td>
            <td data-label="Amount" className="money-cell">{formatInr(item.amount)}</td>
            <td data-label="Bank / UPI">{item.bank_label}<small>{item.upi_label}</small></td>
            <td data-label="Status"><StatusBadge tone={statusTone(item)}>{outcomeLabel(item)}</StatusBadge></td>
            <td data-label="Important date"><small>{date.label}</small>{date.value}</td>
            <td data-label="Actions"><div className="application-row-actions">
              {canEdit && item.status === "PLANNED" && <button type="button" disabled={busy} onClick={() => void update(item, "submit")}>Mark submitted</button>}
              {canEdit && item.status === "SUBMITTED" && <button type="button" disabled={busy} onClick={() => void update(item, "block")}>Mark blocked</button>}
              {canEdit && item.status === "BLOCKED" && <button type="button" disabled={busy} onClick={() => { setResultError(""); setResultId(item.id); }}>Record result</button>}
              {canEdit && (item.status === "PLANNED" || item.status === "SUBMITTED") && <button type="button" className="button-secondary" disabled={busy} onClick={() => void openEdit(item)}>Edit</button>}
              {canEdit && canCancel(item) && <button type="button" className="button-ghost-danger" disabled={busy} onClick={() => setPendingCancelIds([item.id])}>Cancel</button>}
              {item.status === "ALLOTTED" && <Link className="button-secondary" href="/portfolio">View holding</Link>}
              <button type="button" className="button-ghost" onClick={() => setSelectedId(item.id)}>Details</button>
            </div></td>
          </tr>; })}</tbody></table></div>
        </section>;
      })}
      </>}
    </>}
    {selectedItem && <Drawer title={`${selectedItem.applicant_name} · ${selectedItem.ipo_name}`} onClose={() => setSelectedId(null)}>
      <div className="application-detail"><StatusBadge tone={statusTone(selectedItem)}>{outcomeLabel(selectedItem)}</StatusBadge><p>{selectedItem.category === "SHNI" ? "sHNI" : "Retail"} · {selectedItem.lots} {selectedItem.lots === 1 ? "lot" : "lots"} · {formatInr(selectedItem.amount)}</p><p>{selectedItem.bank_label} · {selectedItem.upi_label}</p></div>
      <h3>Progress</h3><ol className="application-timeline">{applicationHistory(selectedItem).map((event, index) => <li key={`${event.at}-${index}`}><time dateTime={event.at}>{displayTime(event.at)}</time><span>{event.label}</span></li>)}</ol>
      {selectedItem.status === "ALLOTTED" && <Link href="/portfolio">View holding →</Link>}
    </Drawer>}
    {editItem && <Drawer title={`Edit ${editItem.applicant_name} · ${editItem.ipo_name}`} onClose={() => setEditId(null)}>
      <p className="intro">Update the application you track here. An earlier plan export will still show its original details. If this was submitted through a broker or bank, update or cancel it there separately.</p>
      {editError && <div className="plan-error" role="alert">{editError}</div>}
      {editLoading ? <p>Loading bank and UPI choices…</p> : <form className="sign-in-form" onSubmit={(event) => void saveEdit(event)}>
        <label htmlFor="application-edit-category">Category</label><select id="application-edit-category" value={editCategory} onChange={(event) => { setEditCategory(event.target.value); if (event.target.value === "RETAIL") setEditLots(1); }}><option value="RETAIL">Retail</option><option value="SHNI">sHNI</option></select>
        <label htmlFor="application-edit-lots">Lots</label><input id="application-edit-lots" type="number" min="1" step="1" required value={editLots} disabled={editCategory === "RETAIL"} onChange={(event) => setEditLots(Number(event.target.value))} />
        <label htmlFor="application-edit-bank">Bank account</label><select id="application-edit-bank" value={editBank} required onChange={(event) => { const bankId = event.target.value; setEditBank(bankId); setEditUpi(upis.find((upi) => upi.bank === bankId && upi.active && upi.verified)?.id ?? ""); }}>{banks.filter((bank) => bank.active && !bank.is_placeholder).map((bank) => <option key={bank.id} value={bank.id}>{bank.bank_name} · {bank.account_display}</option>)}</select>
        <label htmlFor="application-edit-upi">UPI ID</label><select id="application-edit-upi" value={editUpi} required onChange={(event) => setEditUpi(event.target.value)}>{eligibleUpis.map((upi) => <option key={upi.id} value={upi.id}>{upi.handle}</option>)}</select>
        <p className="application-edit-preview">Updated amount: <strong>{formatInr(String(Number(editItem.amount) / editItem.lots * editLots))}</strong></p>
        <button type="submit" disabled={busy || !eligibleUpis.some((upi) => upi.id === editUpi)}>Save changes</button>
      </form>}
    </Drawer>}
    {resultItem && <Drawer title="Record application result" onClose={() => setResultId(null)}>
      <p className="intro">{resultItem.applicant_name} · {resultItem.ipo_name} · {formatInr(resultItem.amount)} blocked</p>
      {resultError && <div className="plan-error" role="alert">{resultError}</div>}
      <p>Recording the result releases the full application block. An allotment also deducts the actual cost from Balance.</p>
      <div className="result-options"><h3>Not allotted</h3><button className="button-secondary" type="button" disabled={busy} onClick={() => void update(resultItem, "not-allotted")}>Record not allotted</button></div>
      <div className="result-options"><h3>Allotted</h3><AllotmentForm item={resultItem} busy={busy} onSave={(quantity, actualCost) => void recordAllotment(resultItem, quantity, actualCost)} /></div>
    </Drawer>}
    {pendingCancelIds.length > 0 && <ConfirmationDialog title={`Cancel ${pendingCancelIds.length} ${pendingCancelIds.length === 1 ? "application" : "applications"}?`} description="Cancelled applications leave the active list and stop using planning slots. The record stays in history. If an application was sent to a broker or bank, cancel it there too and confirm any blocked funds are released." confirmLabel="Cancel application" busy={busy} onCancel={() => setPendingCancelIds([])} onConfirm={() => void bulkUpdate("cancel", pendingCancelIds)} />}
  </div></main>;
}
