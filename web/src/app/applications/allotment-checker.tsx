"use client";

import { useEffect, useRef, useState } from "react";
import type { ApplicationItem } from "./applications-screen";
import { categoryLabel } from "@/lib/application-category";
import { formatInr } from "@/lib/money";
import { sumAmounts } from "@/lib/plan-amount";
import { checkedAmount, initialCheckedDraft, validCheckedDraft, type AllotmentDraft, type RegistrarBid } from "@/lib/allotment-check";

type ReviewRow = { id: string; query_id: string; application: ApplicationItem; state: string; message: string; provider: string; checked_at: string | null; records: RegistrarBid[]; matched_index: number | null; recorded: boolean; recorded_index: number | null; recorded_quantity: number | null; recorded_cost: string | null };
type Check = { id: string; status: string; created_at: string; rows: ReviewRow[] };
const running = (job: Check | null) => job !== null && ["QUEUED", "RUNNING"].includes(job.status);
const pending = (item: ApplicationItem) => !item.is_plan_row && ["SUBMITTED", "BLOCKED"].includes(item.status);

async function readResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return null as T;
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Could not complete this request. Please retry.");
  return data as T;
}

export function AllotmentChecker({ workspaceId, canEdit, items, ipoId, disabled, onRecorded }: {
  workspaceId: string; canEdit: boolean; items: ApplicationItem[]; ipoId: string; disabled: boolean; onRecorded: (changed: ApplicationItem[]) => void;
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
      row.recorded ? { ...initialCheckedDraft(row.application, row.records, row.recorded_index), quantity: String(row.recorded_quantity ?? 0), cost: row.recorded_cost ?? "0.00" } : current[row.id]?.dirty ? current[row.id] : initialCheckedDraft(row.application, row.records, row.matched_index),
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

  const selected = (job?.rows ?? []).filter((row) => !row.recorded && drafts[row.id]?.selected);
  const ready = selected.length > 0 && selected.every((row) => validCheckedDraft(row.application, drafts[row.id], row.matched_index) && row.state !== "EXPIRED");
  const available = items.filter(pending);
  const checkBusy = busy || disabled || loading || running(job);
  const total = sumAmounts(selected.map((row) => /^\d+(?:\.\d{1,2})?$/.test(drafts[row.id].cost) ? drafts[row.id].cost : "0"));

  function edit(row: ReviewRow, change: Partial<AllotmentDraft>) {
    setDrafts((current) => ({ ...current, [row.id]: { ...current[row.id], ...change, dirty: true } }));
    setConfirming(false);
  }
  async function start(all: boolean) {
    if (checkBusy) return;
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
    <div className="allotment-checker-heading"><div><h2>Check allotment</h2><p>Checks saved PANs with the IPO registrar. Review the bids below, then record the results.</p></div>
      {canEdit && <div className="allotment-checker-actions"><button type="button" disabled={checkBusy || !ipoId || !available.some((item) => item.ipo === ipoId)} onClick={() => void start(false)}>Check this IPO</button><button type="button" className="button-secondary" disabled={checkBusy || available.length === 0} onClick={() => void start(true)}>Check all pending IPOs</button></div>}
    </div>
    <p className="allotment-checker-note">Checking keeps your money records unchanged. Only submitted or blocked bids are checked.</p>
    {error && <p className="plan-error" role="alert">{error}</p>}{message && <p className="plan-success" role="status">{message}</p>}
    {job && <details className="allotment-review" open>
      <summary>Review allotment results · {job.rows.filter((row) => !["QUEUED", "CHECKING"].includes(row.state)).length}/{job.rows.length} bids checked{running(job) ? " · Checking…" : ""}</summary>
      <p>Check created <time dateTime={job.created_at}>{new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(job.created_at))}</time>. Edit lots, shares and amount below. Enter 0 only for a verified non-allotment.</p>
      <div className="allotment-review-list">{job.rows.map((row) => {
        const item = row.application;
        const draft = drafts[row.id] ?? initialCheckedDraft(item, row.records, row.matched_index);
        const label = `${item.applicant_name} ${categoryLabel(item.category)}`;
        const needsVerification = row.matched_index === null || draft.sourceIndex !== String(row.matched_index);
        const locked = !canEdit || busy || disabled || running(job) || row.recorded || row.state === "EXPIRED";
        function changeQuantity(quantity: string) { edit(row, { quantity, cost: checkedAmount(item, quantity) }); }
        return <fieldset key={row.id} className={`allotment-review-row${row.recorded ? " is-recorded" : ""}`} disabled={locked}>
          <legend>{label} · {item.ipo_name}</legend>
          <div className="allotment-review-identity"><strong>{item.applicant_name}</strong><span>{item.ipo_name} · {categoryLabel(item.category)}</span><small>{row.recorded ? "Recorded" : row.matched_index !== null ? "Matched bid — review before recording" : row.message}{row.provider ? ` · ${{ kfin: "KFintech", mufg: "MUFG Intime", bigshare: "Bigshare" }[row.provider] ?? row.provider}` : ""}</small></div>
          <div className="allotment-bid-choice"><label>Registrar bid<select aria-label={`${label} registrar bid`} value={draft.sourceIndex} onChange={(event) => { const sourceIndex = event.target.value; const quantity = sourceIndex === "" ? "" : String(row.records[Number(sourceIndex)].quantity); edit(row, { sourceIndex, quantity, cost: checkedAmount(item, quantity), manualVerified: false, selected: false }); }}><option value="">Enter verified result manually</option>{row.records.map((bid, index) => <option key={index} value={String(index)}>{bid.reference || `Bid ${index + 1}`} · Applied {bid.applied ?? "?"} · Allotted {bid.quantity}{bid.category ? ` · ${categoryLabel(bid.category)}` : ""}{bid.demat ? ` · ${bid.demat}` : ""}</option>)}</select></label>
            {needsVerification && <label className="allotment-verify"><input aria-label={`${label} bid identity verified`} type="checkbox" checked={draft.manualVerified} onChange={(event) => edit(row, { manualVerified: event.target.checked })} /> I verified this bid and result</label>}
          </div>
          <label>Lots<input aria-label={`${label} allotted lots`} type="number" min="0" step="1" max={item.lots} value={draft.quantity !== "" && Number(draft.quantity) % item.lot_size === 0 ? Number(draft.quantity) / item.lot_size : ""} placeholder="Partial" onChange={(event) => changeQuantity(event.target.value !== "" && Number.isSafeInteger(Number(event.target.value)) ? String(Number(event.target.value) * item.lot_size) : "")} /></label>
          <label>Shares<input aria-label={`${label} allotted shares`} type="number" min="0" max={item.max_quantity} step="1" value={draft.quantity} onChange={(event) => changeQuantity(event.target.value)} /></label>
          <label>Amount (₹)<input aria-label={`${label} allotment amount`} type="number" min="0" max={item.amount} step="0.01" value={draft.cost} onChange={(event) => edit(row, { cost: event.target.value })} /></label>
          <label className="allotment-record-choice"><input type="checkbox" checked={draft.selected && !row.recorded} aria-label={`Record ${label}`} onChange={(event) => edit(row, { selected: event.target.checked })} />{row.recorded ? "Recorded" : "Record"}</label>
        </fieldset>;
      })}</div>
      {canEdit && !running(job) && <div className="allotment-record-footer"><p>{selected.length} selected · Allotment cost: <strong>{formatInr(total)}</strong>. Recording releases each selected application’s full block and deducts its actual allotment cost.</p>
        {!confirming ? <button type="button" className="application-result-action" disabled={busy || disabled || !ready} onClick={() => setConfirming(true)}>Record selected results</button> : <div role="group" aria-label="Confirm allotment recording"><strong>Confirm these {selected.length} reviewed results?</strong><button type="button" className="application-result-action" disabled={busy || disabled || !ready} onClick={() => void record()}>{busy ? "Recording…" : "Confirm and record results"}</button><button type="button" className="button-secondary" disabled={busy} onClick={() => setConfirming(false)}>Keep reviewing</button></div>}
      </div>}
    </details>}
  </section>;
}
