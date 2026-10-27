"use client";

import { useState } from "react";
import { Drawer } from "@/components/drawer";
import type { IPOSelection } from "./ipo-choice";

export type EligibleAccount = { id: string; name: string; active: boolean };
export type ShareholderTerms = { minimumLots: number; maximumAmount: string; recordDate: string | null; url: string };

export default function ShareholderChoice({ workspaceId, ipoId, accounts, initial, terms, onSaved }: {
  workspaceId: string; ipoId: string; accounts: EligibleAccount[]; initial: IPOSelection;
  terms: ShareholderTerms; onSaved: (choice: IPOSelection) => void;
}) {
  const [open, setOpen] = useState(false);
  const [enabled, setEnabled] = useState(initial.shareholder_preferred ?? false);
  const [eligible, setEligible] = useState<string[]>(initial.shareholder_eligible ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = accounts.filter((item) => item.active);
  const activeIds = new Set(active.map((item) => item.id));
  const selected = eligible.filter((id) => activeIds.has(id));

  async function save() {
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/ipo-decisions/${ipoId}`, {
        method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify({ shareholder_preferred: enabled, shareholder_eligible: selected, ...(enabled ? { decision: "APPLY" } : {}) }),
      });
      if (!response.ok) throw new Error("Shareholder choices could not be saved. Confirm eligible accounts and try again.");
      onSaved(await response.json() as IPOSelection); setOpen(false);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Save failed."); }
    finally { setBusy(false); }
  }

  return <>
    <button className="button-secondary" type="button" onClick={() => { setEnabled(initial.shareholder_preferred ?? false); setEligible(initial.shareholder_eligible ?? []); setError(""); setOpen(true); }}>
      Shareholder preferred{initial.shareholder_preferred ? ` · ${initial.shareholder_eligible?.length ?? 0} eligible` : ""}
    </button>
    {open && <Drawer title="Shareholder eligibility" onClose={() => setOpen(false)}><form className="sign-in-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <p>Confirm which investors held the required shares{terms.recordDate ? <> on <time dateTime={terms.recordDate}>{terms.recordDate}</time></> : " on the record date in the offer document"}. Eligibility is separate for each IPO.</p>
      <p><a href={terms.url} target="_blank" rel="noopener noreferrer">View shareholder terms ↗</a></p>
      <label className="draft-lock-label"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Add shareholder applications</label>
      <p>First cover investors with one Retail lot and eligible investors with the minimum shareholder lots. Then increase shareholder lots up to {new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(terms.maximumAmount))}, before using remaining funds for public sHNI/bHNI upgrades in your selected IPO mode. Minimum: {terms.minimumLots} lot{terms.minimumLots === 1 ? "" : "s"}.</p>
      <fieldset className="shareholder-accounts"><legend>Eligible investors · {selected.length} of {active.length} selected</legend>
        {active.map((account) => <label className="draft-lock-label" key={account.id}><input type="checkbox" checked={selected.includes(account.id)} onChange={(event) => setEligible((current) => event.target.checked ? [...current.filter((id) => id !== account.id), account.id] : current.filter((id) => id !== account.id))} />{account.name}</label>)}
      </fieldset>
      {error && <p role="alert">{error}</p>}
      {enabled && selected.length === 0 && <p>Select at least one eligible investor.</p>}
      <button type="submit" disabled={busy || (enabled && selected.length === 0)}>{busy ? "Saving…" : "Save shareholder choices"}</button>
    </form></Drawer>}
  </>;
}
