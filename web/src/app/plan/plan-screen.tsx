"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Drawer } from "@/components/drawer";
import { formatInr } from "@/lib/money";
import { amountForLots, minimumShniLots, peakConcurrentAmount, sumAmounts } from "@/lib/plan-amount";
import { EmptyState, PageHeader, StatusBadge } from "@/components/ui";
import { canExportPlan, issueMessage, lockedMappings, planStatus, rankedBanks, reviewedMappings, rowIssueMessages, selectableApplicants, selectableDemats, selectableUpis, type BankLookup, type DematLookup, type FundingPreference, type PlanPreview, type PlanRow, type UpiLookup } from "@/lib/plan-presentation";

export type PlanLookups = {
  ipos: Record<string, { name: string; upperPrice: string; lotSize: number; gmpPercent: string | null; closeDate: string; allotmentDate: string }>;
  applicants: Record<string, { name: string; priority: number; active: boolean }>;
  demats: Record<string, DematLookup>;
  banks: Record<string, BankLookup>;
  upis: Record<string, UpiLookup>;
  preferences: Record<string, FundingPreference[]>;
  selectedIpos: { ipo: string; mode: string }[];
  unavailableSelectedIpoCount: number;
  capital: { balance: string; blocked: string; planned: string; available: string } | null;
  latestPlan: { id: string | null; status: "READY" | "BLOCKED" | "CLEARED" | null; planned_total: string } | null;
};

function fundingType(row: PlanRow, lookups: PlanLookups): "Own" | "Preferred" | "Cross-funded" {
  if (lookups.banks[row.bank]?.owner === row.applicant) return "Own";
  if ((lookups.preferences[row.applicant] ?? []).some((item) => item.bank === row.bank && item.enabled)) return "Preferred";
  return "Cross-funded";
}

export default function PlanScreen({ workspaceId, lookups, canEdit }: {
  workspaceId: string;
  lookups: PlanLookups;
  canEdit: boolean;
}) {
  const router = useRouter();
  const [preview, setPreview] = useState<PlanPreview | null>(null);
  const savedPlan = lookups.latestPlan;
  const [clearedPlanId, setClearedPlanId] = useState<string | null>(null);
  const [clearOpen, setClearOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<PlanRow | null>(null);
  const previewRef = useRef<PlanPreview | null>(null);
  const validationSequence = useRef(0);

  function showPreview(next: PlanPreview) {
    previewRef.current = next;
    setPreview(next);
  }

  async function generate() {
    validationSequence.current += 1;
    setValidating(false);
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/planner/preview`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ locked_rows: lockedMappings(previewRef.current?.rows ?? []) }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: unknown } | null;
        throw new Error(typeof body?.detail === "string"
          ? body.detail
          : "We could not create the plan. Check the selected IPOs and account details.");
      }
      const result = await response.json();
      showPreview(result as PlanPreview);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not create the plan.");
    } finally {
      setBusy(false);
    }
  }

  async function updateRow(index: number, changes: Partial<Pick<PlanRow, "applicant" | "category" | "lots" | "demat" | "bank" | "upi" | "locked">>) {
    const current = previewRef.current;
    const previous = current?.rows[index];
    if (!previous) return;
    const lots = changes.lots ?? previous.lots;
    if (!current || !Number.isSafeInteger(lots) || lots < 1) return;
    if (previous.locked && changes.locked !== false) return;
    const ipo = lookups.ipos[previous.ipo];
    if (!ipo) {
      setError("IPO quote details are unavailable. Refresh the page and try again.");
      return;
    }
    const nextRows = [...current.rows];
    nextRows[index] = {
      ...previous,
      ...changes,
      amount: changes.category || changes.lots ? amountForLots(ipo.upperPrice, ipo.lotSize, lots) : previous.amount,
      blocking_reasons: [],
      warnings: changes.bank || changes.applicant ? (lookups.banks[changes.bank ?? previous.bank]?.owner === (changes.applicant ?? previous.applicant) ? [] : ["CROSS_FUNDING"]) : previous.warnings,
    };
    showPreview({ ...current, rows: nextRows, planned_total: sumAmounts(nextRows.map((row) => row.amount)) });
    setValidating(true);
    setError("");
    const sequence = ++validationSequence.current;
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/planner/validate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ rows: nextRows.map((row) => ({
          ipo: row.ipo,
          applicant: row.applicant,
          category: row.category,
          lots: row.lots,
          amount: row.amount,
          demat: row.demat,
          bank: row.bank,
          upi: row.upi,
          locked: row.locked,
        })) }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error("We could not validate this change. Review the row and try again.");
      if (sequence === validationSequence.current) {
        showPreview({ ...result as PlanPreview, uncovered: current.uncovered });
      }
    } catch (caught) {
      if (sequence === validationSequence.current) {
        setError(caught instanceof Error ? caught.message : "We could not check this change.");
      }
    } finally {
      if (sequence === validationSequence.current) setValidating(false);
    }
  }

  async function validatePlan() {
    const current = previewRef.current;
    if (!current) return;
    setValidating(true);
    setError("");
    const sequence = ++validationSequence.current;
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/planner/validate`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ rows: reviewedMappings(current.rows) }),
      });
      if (!response.ok) throw new Error("We could not validate the plan. Try again.");
      const result = await response.json() as PlanPreview;
      if (sequence === validationSequence.current) {
        showPreview({ ...result, uncovered: current.uncovered });
        setMessage(result.status === "READY" ? "Plan checked and ready." : "Plan checked. Resolve the blocking items below.");
      }
    } catch {
      if (sequence === validationSequence.current) setError("We could not validate the plan. Try again.");
    } finally {
      if (sequence === validationSequence.current) setValidating(false);
    }
  }

  async function savePlan() {
    const current = previewRef.current;
    if (!current || !canEdit) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/planner/runs`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ rows: reviewedMappings(current.rows) }),
      });
      if (!response.ok) throw new Error("We could not save this plan. Review the rows and try again.");
      const result = await response.json() as PlanPreview;
      showPreview({ ...result, uncovered: current.uncovered });
      setMessage(result.status === "READY" ? "Plan saved and ready." : "Plan saved with blocking items to resolve.");
      router.refresh();
    } catch { setError("We could not save this plan. Review the rows and try again."); }
    finally { setBusy(false); }
  }

  async function clearSavedPlan() {
    if (!savedPlan?.id || !canEdit) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/planner/runs/${savedPlan.id}/clear`, { method: "POST" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail || "The saved plan could not be cleared. Refresh and try again.");
      }
      setClearedPlanId(savedPlan.id);
      previewRef.current = null;
      setPreview(null);
      setClearOpen(false);
      setMessage("Saved plan cleared. Tracked applications, if any, remain in Applications.");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The saved plan could not be cleared.");
    } finally {
      setBusy(false);
    }
  }

  async function exportCsv(ipoId: string) {
    const current = previewRef.current;
    if (!current || !canExportPlan(current) || validating || busy) return;
    setBusy(true);
    setError("");
    try {
      const savedResponse = await fetch(`/api/workspaces/${workspaceId}/planner/runs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ rows: reviewedMappings(current.rows), reserve_ipo_id: ipoId }),
      });
      const saved = await savedResponse.json();
      if (!savedResponse.ok) throw new Error("We could not save this plan for export.");
      if (saved.status !== "READY") {
        showPreview({ ...saved as PlanPreview, uncovered: current.uncovered });
        throw new Error("The plan changed. Resolve the blocking issues before export.");
      }
      const exportResponse = await fetch(`/api/workspaces/${workspaceId}/planner/runs/${saved.id}/exports`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ format_id: "demat_csv", ipo_id: ipoId }),
      });
      const exportRecord = await exportResponse.json();
      if (!exportResponse.ok) throw new Error("We could not export this plan.");
      const downloadResponse = await fetch(`/api/workspaces/${workspaceId}/planner/runs/${saved.id}/exports/${exportRecord.id}/download`);
      const download = await downloadResponse.json();
      if (!downloadResponse.ok) throw new Error("We could not prepare the download.");
      setMessage("IPO exported. Its planned funds are now reserved.");
      router.refresh();
      const link = document.createElement("a");
      link.href = download.download_url;
      link.rel = "noopener noreferrer";
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not export this plan.");
    } finally {
      setBusy(false);
    }
  }

  function openEdit(index: number) {
    const row = previewRef.current?.rows[index];
    if (!row) return;
    setEditingIndex(index);
    setEditDraft({ ...row });
  }

  function updateDraft(changes: Partial<PlanRow>) {
    setEditDraft((current) => current ? { ...current, ...changes } : current);
  }

  async function saveDraftEdit() {
    if (editingIndex === null || !editDraft) return;
    await updateRow(editingIndex, {
      applicant: editDraft.applicant, demat: editDraft.demat, bank: editDraft.bank,
      upi: editDraft.upi, category: editDraft.category, lots: editDraft.lots,
      locked: editDraft.locked,
    });
    setEditingIndex(null);
    setEditDraft(null);
  }

  return <main className="page settings-page">
    <div className="shell plan-shell">
      <PageHeader eyebrow="Operations / Plan" title="Application plan" description="Review the proposed applications, adjust mappings, then validate and save." />
      <div className="plan-creation-grid">
        <section className="plan-context-card" aria-labelledby="selected-ipos-heading">
          <h2 id="selected-ipos-heading">Selected IPOs</h2>
          {lookups.selectedIpos.length === 0 ? <EmptyState title={lookups.unavailableSelectedIpoCount > 0 ? "Your selected IPOs are closed." : "No IPOs selected."} detail={lookups.unavailableSelectedIpoCount > 0 ? "Choose an open or upcoming IPO before generating a plan." : "Choose an IPO to plan applications."} action={<Link href="/ipos">Review IPOs</Link>} /> : <ul className="selected-ipo-strip">
            {lookups.selectedIpos.map((selection) => <li key={selection.ipo}>
              <strong>{lookups.ipos[selection.ipo]?.name || "Selected IPO"}</strong>
              <span>{selection.mode === "RETAIL_ONLY" ? "Retail Only" : selection.mode === "RETAIL_PLUS_SHNI" ? "Retail + sHNI" : selection.mode === "SHNI_PREFERRED" ? "sHNI Preferred" : "Custom"}</span>
              <small>GMP {lookups.ipos[selection.ipo]?.gmpPercent ?? "—"}% · Closes {lookups.ipos[selection.ipo]?.closeDate ?? "—"}</small>
            </li>)}
          </ul>}
          <Link href="/ipos">Change selection or mode →</Link>
        </section>
        <section className="plan-context-card" aria-labelledby="capital-heading">
          <h2 id="capital-heading">Capital</h2>
          {lookups.capital ? <div className="plan-context-totals">
            <p><span>Balance</span><strong>{formatInr(lookups.capital.balance)}</strong></p>
            <p><span>Blocked</span><strong>{formatInr(lookups.capital.blocked)}</strong></p>
            <p><span>Planned</span><strong>{formatInr(lookups.capital.planned)}</strong></p>
            <p><span>Available</span><strong>{formatInr(lookups.capital.available)}</strong></p>
          </div> : <p>Add a bank and set its Balance to see your money here.</p>}
          <p className="plan-context-help">Planned above counts saved reservations. The draft below is not reserved until saved or exported.</p>
          {canEdit && savedPlan?.id && savedPlan.id !== clearedPlanId && savedPlan.status !== "CLEARED" && Number(savedPlan.planned_total) > 0 && <button className="button-secondary" type="button" disabled={busy} onClick={() => { setError(""); setClearOpen(true); }}>Clear saved plan</button>}
        </section>
      </div>
      <div className="plan-toolbar">
        <button type="button" onClick={generate} disabled={busy || validating || !canEdit || lookups.selectedIpos.length === 0}>{busy ? "Working…" : preview ? "Re-plan unlocked" : "Generate Plan"}</button>
        {preview && <><button className="button-secondary" type="button" onClick={() => void validatePlan()} disabled={busy || validating}>Validate</button><button className="button-secondary" type="button" onClick={() => void savePlan()} disabled={busy || validating || !canEdit}>Save</button></>}
      </div>
      {error && <p className="plan-error" role="alert">{error}</p>}
      {message && <p className="plan-note" role="status">{message}</p>}
      {validating && <p role="status">Checking your changes…</p>}
      {preview && <section aria-live="polite">
        <div className="plan-summary">
          <div><span>Total applications</span><strong>{formatInr(preview.planned_total)}</strong></div>
          <div><span>Applications</span><strong>{preview.rows.length}</strong></div>
          <div><span>Applicants covered</span><strong>{new Set(preview.rows.map((row) => row.applicant)).size}</strong></div>
          <div><span>Retail / sHNI</span><strong>{preview.rows.filter((row) => row.category === "RETAIL").length} / {preview.rows.filter((row) => row.category === "SHNI").length}</strong></div>
          <div><span>Status</span><strong>{validating ? "Checking" : planStatus(preview)}</strong></div>
        </div>
        <p className="plan-note">Highest amount needed at one time in this draft: <strong>{formatInr(peakConcurrentAmount(preview.rows.flatMap((row) => {
          const ipo = lookups.ipos[row.ipo];
          return ipo ? [{ amount: row.amount, closeDate: ipo.closeDate, allotmentDate: ipo.allotmentDate, category: row.category }] : [];
        })))}</strong>. Total applications can exceed today’s Balance when money from an earlier IPO is reused after allotment. Each bank is checked at its application cutoff.</p>
        {!validating && <p className="plan-note" role="status">{preview.planning_only ? "Record-only plan: save and track an application already made. Export is closed; planning ends at midnight IST." : !canExportPlan(preview) ? "⚠ Blocking: Resolve issues before export." : planStatus(preview) === "Warning" ? "Ready to export. Review the highlighted issues first." : "Ready to export."}</p>}
        {preview.audit_issues.length > 0 && <div className="plan-error" role="alert">
          <strong>⚠ Blocking: Resolve these issues before export</strong>
          <ul>{preview.audit_issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issueMessage(issue.code)}</li>)}</ul>
        </div>}
        {preview.uncovered.length > 0 && <p className="plan-note">{preview.uncovered.length} applicant/IPO {preview.uncovered.length === 1 ? "pair" : "pairs"} could not be planned.</p>}
        <details className="plan-breakdown"><summary>Plan summary by IPO and uncovered applicants</summary><div className="plan-breakdown-grid">{lookups.selectedIpos.map((selection) => { const rows = preview.rows.filter((row) => row.ipo === selection.ipo); return <div key={selection.ipo}><strong>{lookups.ipos[selection.ipo]?.name ?? "IPO"}</strong><span>{rows.length} applications · {rows.filter((row) => row.category === "RETAIL").length} Retail · {rows.filter((row) => row.category === "SHNI").length} sHNI</span><span>{formatInr(sumAmounts(rows.map((row) => row.amount)))}</span></div>; })}</div>{preview.uncovered.length > 0 && <p>{preview.uncovered.length} applicant/IPO pairs are uncovered. Review the bank and UPI details below.</p>}</details>
        {preview.rows.length === 0 ? <p className="plan-empty">No applications are in this draft. Select an IPO and check your investors, banks and UPIs.</p> : <div className="draft-ipo-groups">
          {[...new Set(preview.rows.map((row) => row.ipo))].map((ipoId) => <section className="draft-ipo-group" key={ipoId}>
            <div className="draft-ipo-heading"><div><h2>{lookups.ipos[ipoId]?.name ?? "IPO"}</h2><p>{preview.rows.filter((row) => row.ipo === ipoId).length} draft applications</p></div>
              <button type="button" className="button-secondary" onClick={() => void exportCsv(ipoId)} disabled={busy || validating || !canEdit || !canExportPlan(preview)}>Export this IPO CSV</button></div>
            <div className="plan-table-wrap"><table className="plan-table draft-applications-table"><caption>Draft applications for {lookups.ipos[ipoId]?.name ?? "IPO"}</caption>
              <thead><tr><th>Applicant</th><th>Demat</th><th>UPI</th><th>Category</th><th>Lots</th><th>Amount</th><th>Funding Type</th><th><span className="visually-hidden">Edit</span></th></tr></thead>
              <tbody>{preview.rows.map((row, index) => row.ipo !== ipoId ? null : <tr key={`${row.ipo}:${row.applicant}:${index}`}>
                <th scope="row" data-label="Applicant">{lookups.applicants[row.applicant]?.name ?? "Applicant"}{rowIssueMessages(row).length > 0 && <small className="draft-issue">Needs review: {rowIssueMessages(row).join("; ")}</small>}{row.locked && <small>Locked for re-planning</small>}</th>
                <td data-label="Demat">{lookups.demats[row.demat]?.label ?? "Unavailable"}</td>
                <td data-label="UPI">{lookups.upis[row.upi]?.label ?? "Unavailable"}</td>
                <td data-label="Category">{row.category === "SHNI" ? "sHNI" : "Retail"}</td>
                <td data-label="Lots">{row.lots}</td>
                <td data-label="Amount" className="money-cell">{formatInr(row.amount)}</td>
                <td data-label="Funding Type"><StatusBadge tone={fundingType(row, lookups) === "Own" ? "positive" : fundingType(row, lookups) === "Preferred" ? "info" : "warning"}>{fundingType(row, lookups)}</StatusBadge></td>
                <td data-label="Edit"><button type="button" className="button-secondary" disabled={busy || validating || !canEdit} onClick={() => openEdit(index)}>Edit</button></td>
              </tr>)}</tbody>
            </table></div>
          </section>)}
        </div>}
      </section>}
      {clearOpen && <Drawer title="Clear saved plan" onClose={() => setClearOpen(false)}><div className="sign-in-form"><p>The latest saved plan will stop reserving funds. Bank balances and plan history stay as they are. Applications already being tracked keep their own reserved amounts.</p>{error && <p className="plan-error" role="alert">{error}</p>}<button type="button" disabled={busy} onClick={() => void clearSavedPlan()}>{busy ? "Clearing…" : "Clear saved plan"}</button><button className="button-secondary" type="button" disabled={busy} onClick={() => setClearOpen(false)}>Keep plan</button></div></Drawer>}
      {editDraft && editingIndex !== null && <Drawer title="Edit draft application" onClose={() => { setEditDraft(null); setEditingIndex(null); }}><form className="sign-in-form" onSubmit={(event) => { event.preventDefault(); void saveDraftEdit(); }}>
        <p className="intro">{lookups.ipos[editDraft.ipo]?.name ?? "IPO"}</p>
        <label htmlFor="draft-applicant">Applicant</label><select id="draft-applicant" value={editDraft.applicant} onChange={(event) => {
          const applicant = event.target.value;
          const demat = selectableDemats(lookups.demats, applicant)[0];
          const bank = rankedBanks(lookups.banks, lookups.upis, lookups.preferences[applicant] ?? [], applicant).find((option) => !option.disabled);
          const upi = bank && selectableUpis(lookups.upis, bank.id, applicant)[0];
          updateDraft({ applicant, demat: demat?.id ?? editDraft.demat, bank: bank?.id ?? editDraft.bank, upi: upi?.id ?? editDraft.upi });
        }}>{!selectableApplicants(lookups.applicants).some((applicant) => applicant.id === editDraft.applicant) && <option value={editDraft.applicant} disabled>Current applicant unavailable</option>}{selectableApplicants(lookups.applicants).map((applicant) => <option key={applicant.id} value={applicant.id}>{applicant.name}</option>)}</select>
        <label htmlFor="draft-demat">Demat</label><select id="draft-demat" value={editDraft.demat} onChange={(event) => updateDraft({ demat: event.target.value })}>{!selectableDemats(lookups.demats, editDraft.applicant).some((demat) => demat.id === editDraft.demat) && <option value={editDraft.demat} disabled>Current demat unavailable</option>}{selectableDemats(lookups.demats, editDraft.applicant).map((demat) => <option key={demat.id} value={demat.id}>{demat.label}</option>)}</select>
        <label htmlFor="draft-category">Category</label><select id="draft-category" value={editDraft.category} onChange={(event) => {
          const category = event.target.value as "RETAIL" | "SHNI";
          const ipo = lookups.ipos[editDraft.ipo];
          updateDraft({ category, lots: category === "RETAIL" ? 1 : ipo ? minimumShniLots(ipo.upperPrice, ipo.lotSize) : editDraft.lots });
        }}><option value="RETAIL">Retail</option><option value="SHNI">sHNI</option></select>
        <label htmlFor="draft-lots">Lots</label><input id="draft-lots" type="number" min={editDraft.category === "SHNI" && lookups.ipos[editDraft.ipo] ? minimumShniLots(lookups.ipos[editDraft.ipo].upperPrice, lookups.ipos[editDraft.ipo].lotSize) : 1} step="1" value={editDraft.lots} disabled={editDraft.category === "RETAIL"} onChange={(event) => updateDraft({ lots: Number(event.target.value) })} />
        <label htmlFor="draft-bank">Funding bank</label><select id="draft-bank" value={editDraft.bank} onChange={(event) => {
          const bank = event.target.value;
          const upi = selectableUpis(lookups.upis, bank, editDraft.applicant)[0];
          updateDraft({ bank, upi: upi?.id ?? editDraft.upi });
        }}>{!lookups.banks[editDraft.bank] && <option value={editDraft.bank} disabled>Current bank unavailable</option>}{rankedBanks(lookups.banks, lookups.upis, lookups.preferences[editDraft.applicant] ?? [], editDraft.applicant).map((option) => <option key={option.id} value={option.id} disabled={option.disabled}>{option.group}: {lookups.banks[option.id].label}</option>)}</select>
        <label htmlFor="draft-upi">UPI</label><select id="draft-upi" value={editDraft.upi} onChange={(event) => updateDraft({ upi: event.target.value })}>{!selectableUpis(lookups.upis, editDraft.bank, editDraft.applicant).some((upi) => upi.id === editDraft.upi) && <option value={editDraft.upi} disabled>Current UPI unavailable</option>}{selectableUpis(lookups.upis, editDraft.bank, editDraft.applicant).map((upi) => <option key={upi.id} value={upi.id}>{upi.label}</option>)}</select>
        <p className="intro">Amount: {lookups.ipos[editDraft.ipo] ? formatInr(amountForLots(lookups.ipos[editDraft.ipo].upperPrice, lookups.ipos[editDraft.ipo].lotSize, editDraft.lots)) : "—"}</p>
        <label className="draft-lock-label"><input type="checkbox" checked={editDraft.locked} onChange={(event) => updateDraft({ locked: event.target.checked })} /> Keep this application when re-planning</label>
        <button type="submit" disabled={busy || validating}>Save changes</button>
      </form></Drawer>}
      <p><Link href="/">Home</Link></p>
    </div>
  </main>;
}
