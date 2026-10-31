"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import type { ApplicationItem } from "../applications/applications-screen";
import { categoryLabel } from "@/lib/application-category";
import { formatInr } from "@/lib/money";
import { sumAmounts } from "@/lib/plan-amount";
import { checkedAmount, initialCheckedDraft, validCheckedDraft, type AllotmentDraft } from "@/lib/allotment-check";

import { allotmentReviewRows, type ReviewRow } from "@/lib/allotment-review";

function reviewDraft(row: ReviewRow): AllotmentDraft {
  const draft = initialCheckedDraft(row.application, row.records, row.recorded ? row.recorded_index : row.matched_index);
  return row.recorded ? { ...draft, quantity: String(row.recorded_quantity ?? 0), cost: row.recorded_cost ?? "0.00", manualVerified: row.matched_index === null || row.recorded_index !== row.matched_index } : draft;
}

export function AllotmentResultRow({ row, draft, locked, onEdit }: { row: ReviewRow; draft: AllotmentDraft; locked: boolean; onEdit: (change: Partial<AllotmentDraft>) => void }) {
  const item = row.application;
  const label = `${item.ipo_name} · ${item.applicant_name} ${categoryLabel(item.category)}`;
  const needsVerification = row.check_available && !row.recorded && (row.matched_index === null || draft.sourceIndex !== String(row.matched_index));
  const status = row.recorded ? Number(draft.quantity) > 0 ? "Allotted" : "Not allotted" : row.state === "CANCELLED" ? "Cancelled" : row.state === "EXPIRED" ? "Expired" : !row.check_available ? "Not checked" : row.matched_index !== null && !needsVerification ? "Matched" : ({ FOUND: "Review bid", NOT_FOUND: "Not found", UNAVAILABLE: "Unavailable", UNSUPPORTED: "Manual check", CHALLENGE: "Verification", PENDING: "Not published", RATE_LIMITED: "Busy", EXPIRED: "Expired", QUEUED: "Waiting", CHECKING: "Checking" }[row.state] ?? "Review");
  function changeQuantity(quantity: string) { onEdit({ quantity, cost: checkedAmount(item, quantity) }); }
  return <tr className={row.recorded ? "is-recorded" : ""}>
    <td className="allotment-record-cell"><input type="checkbox" disabled={locked} checked={draft.selected && !row.recorded} aria-label={`Record ${label}`} onChange={(event) => onEdit({ selected: event.target.checked })} /></td>
    <th scope="row" title={label}><span className="allotment-person"><span className="allotment-applicant">{item.applicant_name}</span><span className="allotment-category">{categoryLabel(item.category)}</span></span></th>

    <td><input aria-label={`${label} allotted lots`} disabled={locked} type="number" min="0" step="1" max={item.lots} value={draft.quantity !== "" && Number(draft.quantity) % item.lot_size === 0 ? Number(draft.quantity) / item.lot_size : ""} placeholder="—" onChange={(event) => changeQuantity(event.target.value !== "" && Number.isSafeInteger(Number(event.target.value)) ? String(Number(event.target.value) * item.lot_size) : "")} /></td>
    <td><input aria-label={`${label} allotted shares`} disabled={locked} type="number" min="0" max={item.max_quantity} step="1" value={draft.quantity} placeholder="—" onChange={(event) => changeQuantity(event.target.value)} /></td>
    <td><input aria-label={`${label} allotment amount`} disabled={locked} type="number" min="0" max={item.amount} step="0.01" value={draft.cost} placeholder="—" onChange={(event) => onEdit({ cost: event.target.value })} /></td>
    <td><select aria-label={`${label} registrar bid`} disabled={locked} value={draft.sourceIndex} title={row.message} onChange={(event) => {
      const sourceIndex = event.target.value; const quantity = sourceIndex === "" ? "" : String(row.records[Number(sourceIndex)].quantity);
      onEdit({ sourceIndex, quantity, cost: checkedAmount(item, quantity), manualVerified: false, selected: false });
    }}><option value="">{row.recorded ? "Recorded result" : !row.check_available ? row.state === "CANCELLED" ? "—" : "Check to fetch bids" : "Enter verified result"}</option>{row.records.map((bid, index) => <option key={index} value={String(index)}>{bid.reference || `Bid ${index + 1}`} · Applied {bid.applied ?? "?"} · Allotted {bid.quantity}{bid.category ? ` · ${categoryLabel(bid.category)}` : ""}{bid.demat ? ` · ${bid.demat}` : ""}</option>)}</select></td>
    <td title={`${row.message}${row.provider ? ` · ${row.provider}` : ""}`}><div className="allotment-row-status"><span>{status}</span>{needsVerification && <label><input aria-label={`${label} bid identity verified`} disabled={locked} type="checkbox" checked={draft.manualVerified} onChange={(event) => onEdit({ manualVerified: event.target.checked })} />Verify</label>}</div></td>

  </tr>;
}

type Check = { id: string; status: string; created_at: string; rows: ReviewRow[] };
const running = (job: Check | null) => job !== null && ["QUEUED", "RUNNING"].includes(job.status);
const pending = (item: ApplicationItem) => !item.is_plan_row && ["SUBMITTED", "BLOCKED"].includes(item.status);

async function readResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return null as T;
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Could not complete this request. Please retry.");
  return data as T;
}

export function AllotmentChecker({ workspaceId, canEdit, items, ipoId, disabled, onRecorded, onShowAll }: {
  workspaceId: string; canEdit: boolean; items: ApplicationItem[]; ipoId: string; disabled: boolean; onRecorded: (changed: ApplicationItem[]) => void; onShowAll: () => void;
}) {
  const [job, setJob] = useState<Check | null>(null);
  const [drafts, setDrafts] = useState<Record<string, AllotmentDraft>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(true);
  const recordGuard = useRef(false);
  const url = `/api/workspaces/${workspaceId}/allotment/checks`;

  function receive(value: Check | null) {
    setJob(value);
    setDrafts((current) => Object.fromEntries((value?.rows ?? []).map((row) => [row.id,
      row.recorded ? reviewDraft(row) : current[row.id]?.dirty ? current[row.id] : reviewDraft(row),
    ])));
  }

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await readResponse<Check | null>(await fetch(url, { cache: "no-store" }));
        if (!alive) return;
        receive(value);
        if (running(value)) timer = setTimeout(() => void load(), 3000);
      } catch { if (alive) setError("Could not load the latest check. Refresh the page to retry."); }
      finally { if (alive) setLoading(false); }
    }
    void load();
    return () => { alive = false; clearTimeout(timer); };
  }, [url, job?.id, job?.status]);

  const visibleRows = allotmentReviewRows(items, job?.rows ?? []).filter((row) => !ipoId || row.application.ipo === ipoId);
  const selected = visibleRows.filter((row) => row.check_available && !row.recorded && drafts[row.id]?.selected);
  const ready = selected.length > 0 && selected.every((row) => validCheckedDraft(row.application, drafts[row.id], row.matched_index) && row.state !== "EXPIRED");
  const available = items.filter(pending);
  const checkBusy = busy || disabled || loading || running(job);
  const total = sumAmounts(selected.map((row) => /^\d+(?:\.\d{1,2})?$/.test(drafts[row.id].cost) ? drafts[row.id].cost : "0"));

  const released = sumAmounts(selected.map((row) => row.application.amount));

  function edit(row: ReviewRow, change: Partial<AllotmentDraft>) {
    setDrafts((current) => ({ ...current, [row.id]: { ...current[row.id], ...change, dirty: true } }));
    setConfirming(false);
  }
  async function start(all: boolean) {
    if (checkBusy) return;
    if (all) onShowAll();
    setBusy(true); setError(""); setMessage(""); setConfirming(false);
    try { receive(await readResponse<Check>(await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ipos: all ? [] : [ipoId] }) }))); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Check could not start."); }
    finally { setBusy(false); }
  }
  async function record() {
    if (!job || !ready || recordGuard.current) return;
    recordGuard.current = true; setBusy(true); setError("");
    try {
      const rows = selected.map((row) => ({ id: row.id, quantity: Number(drafts[row.id].quantity), actual_cost: drafts[row.id].cost, source_index: drafts[row.id].sourceIndex === "" ? null : Number(drafts[row.id].sourceIndex), manual_verified: drafts[row.id].manualVerified }));
      const result = await readResponse<{ applications: ApplicationItem[]; check: Check }>(await fetch(`${url}/${job.id}/record`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ rows }) }));
      onRecorded(result.applications); receive(result.check); setConfirming(false);
      setMessage(`${result.applications.length} results recorded. Balance, Blocked and Portfolio are updated.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Results could not be recorded."); }
    finally { recordGuard.current = false; setBusy(false); }
  }

  return <section className="allotment-checker" aria-label="IPO allotment checker">
    <div className="allotment-checker-heading"><h2>Allotment results <span>{visibleRows.length} {visibleRows.length === 1 ? "bid" : "bids"}</span></h2>
      {canEdit && <div className="allotment-checker-actions"><button type="button" disabled={checkBusy || !ipoId || !available.some((item) => item.ipo === ipoId)} onClick={() => void start(false)}>Check this IPO</button><button type="button" className="button-secondary" disabled={checkBusy || available.length === 0} onClick={() => void start(true)}>Check all pending IPOs</button></div>}
    </div>
    <p className="allotment-checker-note">Select an IPO above or check all pending IPOs. Only recording changes Balance and Blocked.</p>
    {error && <p className="plan-error" role="alert">{error}</p>}{message && <p className="plan-success" role="status">{message}</p>}
    <div className="allotment-review">
      <div className="allotment-review-meta">{job ? <span>Last check: <time dateTime={job.created_at}>{new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(job.created_at))}</time>{running(job) ? " · Checking…" : ""}</span> : <span>No checks yet</span>}<details><summary>Review guidance</summary><p>Edit lots, shares and amount before selecting rows. Verify unmatched bids. Enter 0 only for a verified non-allotment; an unchecked bid stays blank. Recording deducts the actual cost and releases the full application block.</p></details></div>
      {visibleRows.length === 0 ? <p>No applied bids in this selection.</p> : <div className="allotment-table-wrap"><table className="allotment-results-table" aria-label="Allotment bid results"><thead><tr><th scope="col">Record</th><th scope="col">Applicant / Category</th><th scope="col">Lots</th><th scope="col">Shares</th><th scope="col">Amount (₹)</th><th scope="col">Registrar bid</th><th scope="col">Status</th></tr></thead><tbody>
        {visibleRows.map((row, index) => {
          const draft = row.recorded ? reviewDraft(row) : drafts[row.id] ?? reviewDraft(row);
          const locked = !canEdit || busy || disabled || running(job) || row.recorded || !row.check_available || ["EXPIRED", "CANCELLED"].includes(row.state);
          return <Fragment key={row.id}>{(index === 0 || visibleRows[index - 1].application.ipo !== row.application.ipo) && <tr className="allotment-ipo-group"><th colSpan={7} scope="colgroup">{row.application.ipo_name}</th></tr>}<AllotmentResultRow row={row} draft={draft} locked={locked} onEdit={(change) => edit(row, change)} /></Fragment>;
        })}
      </tbody></table></div>}
      {canEdit && job && !running(job) && <div className="allotment-record-footer"><p>{selected.length} selected · Cost: <strong>{formatInr(total)}</strong> · Block to release: <strong>{formatInr(released)}</strong></p>
        {!confirming ? <button type="button" className="application-result-action" disabled={busy || disabled || !ready} onClick={() => setConfirming(true)}>Record selected results</button> : <div role="group" aria-label="Confirm allotment recording"><strong>Confirm these {selected.length} reviewed results?</strong><button type="button" className="application-result-action" disabled={busy || disabled || !ready} onClick={() => void record()}>{busy ? "Recording…" : "Confirm and record results"}</button><button type="button" className="button-secondary" disabled={busy} onClick={() => setConfirming(false)}>Keep reviewing</button></div>}
      </div>}
    </div>
  </section>;
}
