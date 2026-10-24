"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export type IPOSelection = {
  ipo: string;
  decision: "DEFAULT" | "APPLY" | "SKIP";
  mode: "RETAIL_ONLY" | "RETAIL_PLUS_SHNI" | "SHNI_PREFERRED" | "CUSTOM";
  selected: boolean;
  reason: string;
};

function autoSelectionReason(choice: IPOSelection) {
  switch (choice.reason) {
    case "ISSUE_TYPE_EXCLUDED": return "This IPO type is off in automatic selection.";
    case "OPEN_IPO_AVAILABLE": return "An IPO is open, so upcoming IPOs wait for automatic selection.";
    case "WAITING_FOR_FUND_REUSE": return "Automatic selection is waiting for funds from an earlier IPO.";
    case "IPO_NOT_OPEN": return "This IPO is not open for automatic selection.";
    case "THRESHOLD_NOT_SET": return "Set a GMP threshold to turn on automatic selection.";
    case "GMP_UNAVAILABLE": return "No GMP is available for automatic selection.";
    case "BELOW_GMP_THRESHOLD": return "The last GMP is below your threshold.";
    default: return "";
  }
}

export default function IPOChoice({ workspaceId, ipoId, initial, canEdit, automaticEnabled, recordOnly = false }: {
  workspaceId: string;
  ipoId: string;
  initial: IPOSelection | undefined;
  canEdit: boolean;
  automaticEnabled: boolean;
  recordOnly?: boolean;
}) {
  const [choice, setChoice] = useState<IPOSelection>(initial ?? { ipo: ipoId, decision: "DEFAULT", mode: "RETAIL_ONLY", selected: false, reason: "GMP_UNAVAILABLE" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const router = useRouter();

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
      setMessage("");
      router.refresh();
    } catch {
      setMessage("We could not save this choice. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="ipo-choice">
    {automaticEnabled && choice.decision === "DEFAULT" && !choice.selected && autoSelectionReason(choice) && <p className="selection-rule">{autoSelectionReason(choice)}</p>}
    {canEdit && <div className="ipo-choice-buttons">
      {automaticEnabled && <button type="button" disabled={busy} aria-pressed={choice.decision === "DEFAULT"} onClick={() => save({ decision: "DEFAULT" })}>Automatic</button>}
      <button type="button" disabled={busy} aria-pressed={choice.decision === "APPLY"} onClick={() => save({ decision: choice.decision === "APPLY" ? "SKIP" : "APPLY" })}>{choice.decision === "APPLY" ? "Unselect" : recordOnly ? "Select manually" : "Select"}</button>
      <button type="button" disabled={busy} aria-pressed={choice.decision === "SKIP"} onClick={() => save({ decision: "SKIP" })}>Skip</button>
    </div>}
    {choice.selected && <div className="ipo-mode-stack"><label className="ipo-mode">IPO mode
      <select value={choice.mode} disabled={!canEdit || busy} onChange={(event) => save({ mode: event.target.value as IPOSelection["mode"] })}>
        <option value="RETAIL_ONLY">Retail Only</option>
        <option value="RETAIL_PLUS_SHNI">Retail + sHNI</option>
        <option value="SHNI_PREFERRED">sHNI Preferred</option>
        <option value="CUSTOM">Custom</option>
      </select>
    </label>
    {(choice.mode === "RETAIL_PLUS_SHNI" || choice.mode === "SHNI_PREFERRED") && <p className="ipo-mode-help">{choice.mode === "RETAIL_PLUS_SHNI"
      ? "Start with Retail coverage, then try an sHNI upgrade pass where funds allow."
      : "Start with Retail coverage, then repeat upgrades to fit as many minimum sHNI applications as possible."}</p>}</div>}
    {message && <p role="status">{message}</p>}
  </div>;
}
