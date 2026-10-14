"use client";

import { ChangeEvent, FormEvent, useState } from "react";

type ImportRow = {
  row_number: number; name: string; pan_masked: string; type: string;
  dpid_masked: string; client_id_masked: string; upi_masked: string;
  account_masked: string; bank_name: string; payment_reference: string;
  payment_pending: boolean; errors: string[];
};
type ImportPreview = {
  id: string; status: "PREVIEWED" | "CONFIRMED"; source_filename: string;
  row_count: number; error_count: number; rows: ImportRow[];
};
const selectable = (row: ImportRow) => row.errors.length === 0;

export default function AccountImport({ workspaceId, canEdit }: { workspaceId: string; canEdit: boolean }) {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true); setMessage(""); setPreview(null);
    const body = new FormData(); body.append("file", file);
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/account-imports`, { method: "POST", body });
      if (!response.ok) {
        const result = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(result.detail ?? "We could not read that workbook.");
      }
      const data = await response.json() as ImportPreview;
      setPreview(data);
      setSelected(data.rows.filter(selectable).map((row) => row.row_number));
      if (!data.rows.some(selectable)) setMessage("No rows can be imported yet. Correct the errors in the workbook and upload it again.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "We could not read that workbook.");
    } finally { setBusy(false); event.target.value = ""; }
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preview || selected.length === 0) return;
    setBusy(true); setMessage("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/account-imports/${preview.id}`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ row_numbers: selected }),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => ({})) as { detail?: string; errors?: Record<string, string[]> };
        const rowErrors = Object.entries(result.errors ?? {}).map(([row, errors]) => `Row ${row}: ${errors.join(" ")}`).join(" ");
        throw new Error(rowErrors || result.detail || "The selected rows could not be imported.");
      }
      const result = await response.json() as { imported_rows: number; created: { payment_pending: number } };
      setPreview({ ...preview, status: "CONFIRMED" });
      setMessage(`${result.imported_rows} row(s) imported. ${result.created.payment_pending} need their own payment details before IPO planning.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The selected rows could not be imported.");
    } finally { setBusy(false); }
  }

  return <section className="account-import" aria-labelledby="account-import-heading">
    <h2 id="account-import-heading">Import accounts</h2>
    <p>Upload one workbook to add investors and demats. Missing bank details can be added later; the UPI prefix is shown as a reference, never as a bank account number. Payment details must belong to the applicant before IPO planning.</p>
    {canEdit && <label className="file-picker">Choose workbook
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={busy} onChange={upload} />
    </label>}
    {preview && <form onSubmit={confirm}>
      <p><strong>{preview.source_filename}</strong> · {preview.row_count} row(s), {preview.error_count} with errors · {preview.rows.filter((row) => row.payment_pending).length} payment setups pending</p>
      <div className="plan-table-wrap"><table className="plan-table account-import-table">
        <caption>Review import rows</caption>
        <thead><tr><th>Import</th><th>Name</th><th>PAN</th><th>Demat</th><th>UPI</th><th>Bank details</th><th>Status</th></tr></thead>
        <tbody>{preview.rows.map((row) => {
          const checked = selected.includes(row.row_number);
          const canSelect = selectable(row);
          return <tr key={row.row_number}>
            <td data-label="Import"><input type="checkbox" aria-label={`Import row ${row.row_number} for ${row.name}`} checked={checked} disabled={!canEdit || busy || !canSelect || preview.status === "CONFIRMED"} onChange={(event) => setSelected((current) => event.target.checked ? [...current, row.row_number] : current.filter((number) => number !== row.row_number))} /></td>
            <td data-label="Name" title={row.name}>{row.name}</td><td data-label="PAN">{row.pan_masked}</td>
            <td data-label="Demat" title={`${row.type} · ${row.dpid_masked} · ${row.client_id_masked}`}>{row.type} · {row.dpid_masked} · {row.client_id_masked}</td>
            <td data-label="UPI" title={row.upi_masked}>{row.upi_masked}</td>
            <td data-label="Bank details">{row.payment_pending ? <span>Bank to add later · UPI ref {row.payment_reference}</span> : <span>{row.bank_name} · {row.account_masked}</span>}</td>
            <td data-label="Status">{preview.status === "CONFIRMED" && checked ? "Imported" : canSelect ? row.payment_pending ? "Payment pending" : "Ready" : <details className="import-row-errors"><summary>{row.errors.length} {row.errors.length === 1 ? "issue" : "issues"}</summary><ul>{row.errors.map((error) => <li key={error}>{error}</li>)}</ul></details>}</td>
          </tr>;
        })}</tbody>
      </table></div>
      {canEdit && preview.status === "PREVIEWED" && <button type="submit" disabled={busy || selected.length === 0}>Import selected ({selected.length})</button>}
      {preview.status === "CONFIRMED" && <button type="button" className="button-secondary" onClick={() => window.location.reload()}>Refresh Settings</button>}
    </form>}
    {message && <p role="status">{message}</p>}
  </section>;
}
