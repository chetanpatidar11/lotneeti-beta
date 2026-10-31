"use client";

import Link from "next/link";
import { useState } from "react";
import { appliedIpos } from "@/lib/applied-ipos";
import { PageHeader } from "@/components/ui";
import type { ApplicationItem } from "../applications/applications-screen";
import { AllotmentChecker } from "./allotment-checker";

export default function CheckAllotmentScreen({ workspaceId, canEdit, initialItems, initialLoadError = false }: {
  workspaceId: string; canEdit: boolean; initialItems: ApplicationItem[]; initialLoadError?: boolean;
}) {
  const [items, setItems] = useState(initialItems);
  const [ipoId, setIpoId] = useState("");
  const ipos = appliedIpos(items);
  const hasPending = items.some((item) => !item.is_plan_row && ["SUBMITTED", "BLOCKED"].includes(item.status));

  function updateApplications(changed: ApplicationItem[]) {
    const byId = new Map(changed.map((item) => [item.id, item]));
    setItems((current) => current.map((item) => byId.get(item.id) ?? item));
  }

  return <main className="page"><div className="shell applications-shell">
    <PageHeader eyebrow="Results" title="Check Allotment" description="Check your IPO bids, review the allotment and record the results when ready." />
    {initialLoadError ? <div className="plan-error" role="alert">Applications could not be loaded. <button type="button" className="button-ghost" onClick={() => window.location.reload()}>Retry</button></div> : <>
      <section className="applied-ipos" aria-label="Applied IPOs">
        <div className="applied-ipos-heading"><h2>Applied IPOs <span>{ipos.length}</span></h2><label className="allotment-one-ipo" htmlFor="allotment-ipo-choice">Check one IPO<select id="allotment-ipo-choice" value={ipoId} onChange={(event) => setIpoId(event.target.value)}><option value="">All applied IPOs</option>{ipos.map((ipo) => <option key={ipo.id} value={ipo.id}>{ipo.name}</option>)}</select></label><button type="button" className="button-secondary" aria-pressed={!ipoId} onClick={() => setIpoId("")}>All applied IPOs</button></div>
        {ipos.length === 0 ? <p>No applied IPOs yet. Mark applied bids submitted in <Link href="/applications">Applications</Link>.</p> : <div className="allotment-table-wrap"><table className="applied-ipos-table"><thead><tr><th scope="col">IPO</th><th scope="col">Applied</th><th scope="col">Pending</th><th scope="col">Recorded</th></tr></thead><tbody>
          {ipos.map((ipo) => <tr key={ipo.id} className={ipoId === ipo.id ? "is-active" : ""}><th scope="row"><button type="button" className="applied-ipo-name" aria-pressed={ipoId === ipo.id} title={ipo.name} onClick={() => setIpoId(ipoId === ipo.id ? "" : ipo.id)}>{ipo.name}</button></th><td>{ipo.total}</td><td>{ipo.pending}</td><td title={`${ipo.allotted} allotted · ${ipo.notAllotted} not allotted · ${ipo.cancelled} cancelled`}>{ipo.allotted + ipo.notAllotted}</td></tr>)}
        </tbody></table></div>}
      </section>
      {!hasPending && <p>No submitted or blocked bids are waiting for a result. You can manage bids in <Link href="/applications">Applications</Link> and review your latest check below.</p>}
      <AllotmentChecker workspaceId={workspaceId} canEdit={canEdit} items={items} ipoId={ipoId} disabled={false} onRecorded={updateApplications} onShowAll={() => setIpoId("")} />
    </>}
  </div></main>;
}
