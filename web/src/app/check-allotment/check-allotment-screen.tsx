"use client";

import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/ui";
import type { ApplicationItem } from "../applications/applications-screen";
import { AllotmentChecker } from "./allotment-checker";

export default function CheckAllotmentScreen({ workspaceId, canEdit, initialItems, initialLoadError = false }: {
  workspaceId: string; canEdit: boolean; initialItems: ApplicationItem[]; initialLoadError?: boolean;
}) {
  const [items, setItems] = useState(initialItems);
  const [ipoId, setIpoId] = useState("");
  const ipos = [...new Map(items.map((item) => [item.ipo, { name: item.ipo_name, closeDate: item.close_date }])).entries()]
    .sort((left, right) => right[1].closeDate.localeCompare(left[1].closeDate) || left[1].name.localeCompare(right[1].name));
  const hasPending = items.some((item) => !item.is_plan_row && ["SUBMITTED", "BLOCKED"].includes(item.status));

  function updateApplications(changed: ApplicationItem[]) {
    const byId = new Map(changed.map((item) => [item.id, item]));
    setItems((current) => current.map((item) => byId.get(item.id) ?? item));
  }

  return <main className="page"><div className="shell applications-shell">
    <PageHeader eyebrow="Results" title="Check Allotment" description="Check your IPO bids, review the allotment and record the results when ready." />
    {initialLoadError ? <div className="plan-error" role="alert">Applications could not be loaded. <button type="button" className="button-ghost" onClick={() => window.location.reload()}>Retry</button></div> : <>
      <section className="allotment-ipo-picker" aria-label="Allotment IPO selection">
        <label htmlFor="allotment-ipo-choice">Select an IPO</label>
        <select id="allotment-ipo-choice" value={ipoId} onChange={(event) => setIpoId(event.target.value)}>
          <option value="">Select an IPO</option>
          {ipos.map(([id, ipo]) => <option key={id} value={id}>{ipo.name}</option>)}
        </select>
      </section>
      {!hasPending && <p>No submitted or blocked bids are waiting for a result. You can manage bids in <Link href="/applications">Applications</Link> and review your latest check below.</p>}
      <AllotmentChecker workspaceId={workspaceId} canEdit={canEdit} items={items} ipoId={ipoId} disabled={false} onRecorded={updateApplications} />
    </>}
  </div></main>;
}
