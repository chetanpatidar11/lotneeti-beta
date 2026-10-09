"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function ThresholdSetting({
  workspaceId,
  initialValue,
  canEdit,
}: {
  workspaceId: string;
  initialValue: string | null;
  canEdit: boolean;
}) {
  const [value, setValue] = useState(initialValue ?? "");
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
        body: JSON.stringify({ auto_select_gmp_percent: value === "" ? null : value }),
      });
      if (!response.ok) throw new Error("Save failed");
      setMessage("GMP threshold saved.");
      router.refresh();
    } catch {
      setMessage("We could not save the threshold. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="threshold-setting">
    <h2>Automatic IPO selection</h2>
    <p>Set the minimum GMP percentage for draft selection. You can still choose Apply or Skip for each IPO.</p>
    {canEdit ? <form onSubmit={save}>
      <label>GMP threshold (%)
        <input type="number" step="0.01" value={value} onChange={(event) => setValue(event.target.value)} placeholder="Not set" />
      </label>
      <button type="submit" disabled={busy}>Save threshold</button>
    </form> : <p>GMP threshold: {value === "" ? "Not set" : `${value}%`}</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
