"use client";

import { Drawer } from "@/components/drawer";
import { categoryLabel } from "@/lib/application-category";
import { amountForLots, minimumBhniLots, minimumShniLots } from "@/lib/plan-amount";
import { formatInr } from "@/lib/money";
import { rankedBanks, selectableApplicants, selectableDemats, selectableUpis, type PlanRow } from "@/lib/plan-presentation";
import type { PlanLookups } from "./plan-screen";

export default function DraftApplicationEditor({ draft, lookups, busy, onChange, onSave, onClose }: {
  draft: PlanRow; lookups: PlanLookups; busy: boolean; onChange: (changes: Partial<PlanRow>) => void;
  onSave: () => Promise<void>; onClose: () => void;
}) {
  const ipo = lookups.ipos[draft.ipo];
  const asbaBanks = Object.entries(lookups.banks).filter(([, bank]) => bank.active && bank.asbaReady && bank.owner === draft.applicant).sort(([a], [b]) => a.localeCompare(b));
  const bankChoices = draft.category === "BHNI" ? asbaBanks.map(([id]) => ({ id, group: "Own ASBA bank", disabled: false })) : rankedBanks(lookups.banks, lookups.upis, lookups.preferences[draft.applicant] ?? [], draft.applicant);
  const minimum = !ipo ? 1 : draft.category === "BHNI" ? minimumBhniLots(ipo.upperPrice, ipo.lotSize) : draft.category === "SHNI" ? minimumShniLots(ipo.upperPrice, ipo.lotSize) : draft.category === "SHARE" ? ipo.shareholderMinLots ?? 1 : 1;
  const validLots = Number.isSafeInteger(draft.lots) && draft.lots >= minimum;
  const applicants = selectableApplicants(lookups.applicants).filter((item) => draft.category !== "SHARE" || ipo?.shareholderEligible?.includes(item.id));
  const upis = selectableUpis(lookups.upis, draft.bank, draft.applicant);

  function changeCategory(category: PlanRow["category"]) {
    const bank = category === "BHNI" ? asbaBanks.find(([id]) => id === draft.bank)?.[0] ?? asbaBanks[0]?.[0] ?? "" : draft.bank;
    onChange({ category, bank, upi: category === "BHNI" ? "" : selectableUpis(lookups.upis, bank, draft.applicant)[0]?.id ?? "", lots: !ipo ? 1 : category === "BHNI" ? minimumBhniLots(ipo.upperPrice, ipo.lotSize) : category === "SHNI" ? minimumShniLots(ipo.upperPrice, ipo.lotSize) : 1 });
  }

  return <Drawer title="Edit draft application" onClose={onClose}><form className="sign-in-form" onSubmit={(event) => { event.preventDefault(); if (validLots) void onSave(); }}>
    <p>{ipo?.name ?? "Selected IPO"}</p>
    <label htmlFor="draft-applicant">Applicant</label><select id="draft-applicant" value={draft.applicant} onChange={(event) => {
      const applicant = event.target.value;
      const demat = selectableDemats(lookups.demats, applicant)[0]?.id ?? "";
      const bank = draft.category === "BHNI" ? Object.entries(lookups.banks).find(([, item]) => item.active && item.asbaReady && item.owner === applicant)?.[0] ?? "" : rankedBanks(lookups.banks, lookups.upis, lookups.preferences[applicant] ?? [], applicant).find((item) => !item.disabled)?.id ?? "";
      onChange({ applicant, demat, bank, upi: draft.category === "BHNI" ? "" : selectableUpis(lookups.upis, bank, applicant)[0]?.id ?? "" });
    }}>{!applicants.some((item) => item.id === draft.applicant) && <option value={draft.applicant} disabled>Current applicant unavailable</option>}{applicants.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
    <label htmlFor="draft-demat">Demat</label><select id="draft-demat" value={draft.demat} onChange={(event) => onChange({ demat: event.target.value })}>{selectableDemats(lookups.demats, draft.applicant).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
    <label htmlFor="draft-category">Category</label><select id="draft-category" value={draft.category} onChange={(event) => changeCategory(event.target.value as PlanRow["category"])}>{(draft.category === "SHARE" ? ["SHARE"] : ["RETAIL", "SHNI", "BHNI"]).map((category) => <option key={category} value={category}>{categoryLabel(category)}</option>)}</select>
    <label htmlFor="draft-lots">Lots</label><input id="draft-lots" type="number" min={minimum} step="1" required value={draft.lots || ""} onChange={(event) => onChange({ lots: Number(event.target.value) })} />
    <p>Whole lots only. Retail/Shareholder: up to ₹2 lakh. sHNI: above ₹2 lakh through ₹10 lakh. bHNI: above ₹10 lakh using own-bank ASBA.</p>
    <label htmlFor="draft-bank">Funding bank</label><select id="draft-bank" value={draft.bank} required onChange={(event) => onChange({ bank: event.target.value, upi: draft.category === "BHNI" ? "" : selectableUpis(lookups.upis, event.target.value, draft.applicant)[0]?.id ?? "" })}>
      {!bankChoices.some((item) => item.id === draft.bank) && <option value="">Choose an available bank</option>}{bankChoices.map((item) => <option key={item.id} value={item.id} disabled={item.disabled}>{item.group}: {lookups.banks[item.id].label}</option>)}
    </select>
    {draft.category === "BHNI" ? <p>Bank ASBA · UPI is not used. Complete an own-bank account number in Settings if no bank is available.</p> : <><label htmlFor="draft-upi">UPI</label><select id="draft-upi" value={draft.upi} required onChange={(event) => onChange({ upi: event.target.value })}>{!upis.some((item) => item.id === draft.upi) && <option value="">Choose a linked UPI</option>}{upis.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></>}
    <p className="intro">Amount: {ipo && validLots ? formatInr(amountForLots(ipo.upperPrice, ipo.lotSize, draft.lots)) : "—"}</p>
    <label className="draft-lock-label"><input type="checkbox" checked={draft.locked} onChange={(event) => onChange({ locked: event.target.checked })} /> Keep this application when re-planning</label>
    <button type="submit" disabled={busy || !validLots}>Save changes</button>
  </form></Drawer>;
}
