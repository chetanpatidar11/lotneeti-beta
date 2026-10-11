"use client";

import { ChangeEvent, FormEvent, useState } from "react";

type ImportRow = {
  row_number: number; name: string; pan_masked: string; type: string;
  dpid_masked: string; client_id_masked: string; upi_masked: string;
  account_masked: string; bank_name: string; errors: string[];
};
type ImportPreview = {
  id: string; status: "PREVIEWED" | "CONFIRMED"; source_filename: string;
  row_count: number; error_count: number; rows: ImportRow[];
};
type BankDetails = { account_number: string; bank_name: string };
const missingAccount = "Account Number is required.";
const missingBank = "Bank Name is required.";
const repairable = (row: ImportRow) => row.errors.every((error) => error === missingAccount || error === missingBank);

export default function AccountImport({ workspaceId, canEdit }: { workspaceId: string; canEdit: boolean }) {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [details, setDetails] = useState<Record<number, BankDetails>>({});
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
      setSelected(data.rows.filter(repairable).map((row) => row.row_number));
      setDetails({});
      if (!data.rows.some(repairable)) setMessage("No rows can be imported yet. Correct the other errors in the workbook and upload it again.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "We could not read that workbook.");
    } finally { setBusy(false); event.target.value = ""; }
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preview || selected.length === 0) return;
    setBusy(true); setMessage("");
    try {
      const bank_details = Object.fromEntries(selected.map((rowNumber) => [String(rowNumber), details[rowNumber] ?? {}]));
      const response = await fetch(`/api/workspaces/${workspaceId}/account-imports/${preview.id}`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ row_numbers: selected, bank_details }),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => ({})) as { detail?: string; errors?: Record<string, string[]> };
        const rowErrors = Object.entries(result.errors ?? {}).map(([row, errors]) => `Row ${row}: ${errors.join(" ")}`).join(" ");
        throw new Error(rowErrors || result.detail || "The selected rows could not be imported.");
      }
      const result = await response.json() as { imported_rows: number };
      setPreview({ ...preview, status: "CONFIRMED" });
      setDetails({});
      setMessage(`${result.imported_rows} row(s) imported. Set each bank Balance before planning.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The selected rows could not be imported.");
    } finally { setBusy(false); }
  }

  function updateDetail(rowNumber: number, field: keyof BankDetails, value: string) {
    setDetails((current) => ({ ...current, [rowNumber]: { account_number: current[rowNumber]?.account_number ?? "", bank_name: current[rowNumber]?.bank_name ?? "", [field]: value } }));
  }

  return <section className="account-import" aria-labelledby="account-import-heading">
    <h2 id="account-import-heading">Import accounts</h2>
    <p>Review the workbook before importing. Enter a missing account number or bank name below. Rows with other errors need a corrected workbook. Each PAN may appear only once.</p>
    {canEdit && <label className="file-picker">Choose workbook
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={busy} onChange={upload} />
    </label>}
    {preview && <form onSubmit={confirm}>
      <p><strong>{preview.source_filename}</strong> · {preview.row_count} row(s), {preview.error_count} needing attention</p>
      <div className="plan-table-wrap"><table className="plan-table account-import-table">
        <caption>Review import rows</caption>
        <thead><tr><th>Import</th><th>Name</th><th>PAN</th><th>Demat</th><th>UPI</th><th>Bank details</th><th>Status</th></tr></thead>
        <tbody>{preview.rows.map((row) => {
          const checked = selected.includes(row.row_number);
          const canSelect = repairable(row);
          return <tr key={row.row_number}>
            <td data-label="Import"><input type="checkbox" aria-label={`Import row ${row.row_number} for ${row.name}`} checked={checked} disabled={!canEdit || busy || !canSelect || preview.status === "CONFIRMED"} onChange={(event) => setSelected((current) => event.target.checked ? [...current, row.row_number] : current.filter((number) => number !== row.row_number))} /></td>
            <td data-label="Name">{row.name}</td><td data-label="PAN">{row.pan_masked}</td>
            <td data-label="Demat">{row.type} · {row.dpid_masked} · {row.client_id_masked}</td>
            <td data-label="UPI">{row.upi_masked}</td>
            <td data-label="Bank details"><div className="import-bank-details">
              {row.errors.includes(missingAccount) ? preview.status === "CONFIRMED" ? <span>{checked ? "Account number added" : "Not imported"}</span> : <label>Account number<input type="text" inputMode="numeric" autoComplete="off" maxLength={40} required={checked} disabled={!checked || busy} value={details[row.row_number]?.account_number ?? ""} onChange={(event) => updateDetail(row.row_number, "account_number", event.target.value)} /></label> : <span>{row.account_masked}</span>}
              {row.errors.includes(missingBank) ? preview.status === "CONFIRMED" ? <span>{checked ? "Bank name added" : "Not imported"}</span> : <label>Bank name<input type="text" maxLength={120} required={checked} disabled={!checked || busy} value={details[row.row_number]?.bank_name ?? ""} onChange={(event) => updateDetail(row.row_number, "bank_name", event.target.value)} /></label> : <span>{row.bank_name}</span>}
            </div></td>
            <td data-label="Status">{preview.status === "CONFIRMED" && checked ? "Imported" : canSelect ? row.errors.length ? "Fill missing bank details" : "Ready" : <ul>{row.errors.map((error) => <li key={error}>{error}</li>)}</ul>}</td>
          </tr>;
        })}</tbody>
      </table></div>
      {canEdit && preview.status === "PREVIEWED" && <button type="submit" disabled={busy || selected.length === 0}>Import selected ({selected.length})</button>}
      {preview.status === "CONFIRMED" && <button type="button" className="button-secondary" onClick={() => window.location.reload()}>Refresh Settings</button>}
    </form>}
    {message && <p role="status">{message}</p>}
  </section>;
}
