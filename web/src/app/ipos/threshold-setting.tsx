"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function ThresholdSetting({
  workspaceId,
  initialValue,
  initialIssueTypes,
  canEdit,
}: {
  workspaceId: string;
  initialValue: string | null;
  initialIssueTypes: string[];
  canEdit: boolean;
}) {
  const [value, setValue] = useState(initialValue ?? "");
  const [issueTypes, setIssueTypes] = useState(initialIssueTypes.length ? initialIssueTypes : ["MAINBOARD"]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const router = useRouter();

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ auto_select_gmp_percent: value === "" ? null : value, auto_select_issue_types: issueTypes }),
      });
      if (!response.ok) throw new Error("Save failed");
      setMessage("Automatic selection saved.");
      router.refresh();
    } catch {
      setMessage("We could not save automatic selection. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="threshold-setting">
    <h2>Automatic IPO selection</h2>
    <p>Choose which IPO types can be selected automatically when they meet the GMP threshold. Manual Apply and Skip choices still win.</p>
    {canEdit ? <form onSubmit={save}>
      <label>GMP threshold (%)
        <input type="number" step="0.01" value={value} onChange={(event) => setValue(event.target.value)} placeholder="Not set" />
      </label>
      <fieldset className="auto-issue-types"><legend>IPO types</legend>
        {([["MAINBOARD", "Mainboard"], ["SME", "SME"]] as const).map(([id, label]) => <label key={id}><input type="checkbox" checked={issueTypes.includes(id)} onChange={() => setIssueTypes((current) => current.includes(id) ? current.length > 1 ? current.filter((item) => item !== id) : current : [...current, id])} />{label}</label>)}
      </fieldset>
      <button type="submit" disabled={busy}>Save selection</button>
    </form> : <p>GMP threshold: {value === "" ? "Not set" : `${value}%`} · IPO types: {issueTypes.join(" + ")}</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
