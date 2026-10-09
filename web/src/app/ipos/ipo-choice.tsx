"use client";

import { useState } from "react";
import { StatusBadge } from "@/components/ui";

export type IPOSelection = {
  ipo: string;
  decision: "DEFAULT" | "APPLY" | "SKIP";
  mode: "RETAIL_ONLY" | "RETAIL_PLUS_SHNI" | "SHNI_PREFERRED" | "CUSTOM";
  selected: boolean;
  reason: string;
};

export default function IPOChoice({ workspaceId, ipoId, initial, canEdit }: {
  workspaceId: string;
  ipoId: string;
  initial: IPOSelection | undefined;
  canEdit: boolean;
}) {
  const [choice, setChoice] = useState<IPOSelection>(initial ?? { ipo: ipoId, decision: "DEFAULT", mode: "RETAIL_ONLY", selected: false, reason: "NO_AUTO_SELECTION" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function save(changes: Partial<Pick<IPOSelection, "decision" | "mode">>) {
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/ipo-decisions/${ipoId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(changes),
      });
      if (!response.ok) throw new Error("Save failed");
      setChoice((await response.json()) as IPOSelection);
      setMessage("IPO choice saved.");
    } catch {
      setMessage("We could not save this choice. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const label = choice.decision === "APPLY" ? "Manually selected" : choice.decision === "SKIP" ? "Manually skipped" : choice.selected ? "Auto selected" : "Not selected";
  return <div className="ipo-choice">
    <p><StatusBadge tone={choice.decision === "SKIP" ? "danger" : choice.selected ? "positive" : "neutral"}>{label}</StatusBadge>{choice.decision === "DEFAULT" && <small className="selection-rule">{choice.selected ? "Matches your auto-select rule" : "Does not match your auto-select rule"}</small>}</p>
    {canEdit && <div className="ipo-choice-buttons">
      <button type="button" disabled={busy} aria-pressed={choice.decision === "DEFAULT"} onClick={() => save({ decision: "DEFAULT" })}>Automatic</button>
      <button type="button" disabled={busy} aria-pressed={choice.decision === "APPLY"} onClick={() => save({ decision: "APPLY" })}>Apply</button>
      <button type="button" disabled={busy} aria-pressed={choice.decision === "SKIP"} onClick={() => save({ decision: "SKIP" })}>Skip</button>
    </div>}
    {choice.selected && <label className="ipo-mode">IPO mode
      <select value={choice.mode} disabled={!canEdit || busy} onChange={(event) => save({ mode: event.target.value as IPOSelection["mode"] })}>
        <option value="RETAIL_ONLY">Retail Only</option>
        <option value="RETAIL_PLUS_SHNI">Retail + sHNI</option>
        <option value="SHNI_PREFERRED">sHNI Preferred</option>
        <option value="CUSTOM">Custom</option>
      </select>
    </label>}
    {message && <p role="status">{message}</p>}
  </div>;
}
