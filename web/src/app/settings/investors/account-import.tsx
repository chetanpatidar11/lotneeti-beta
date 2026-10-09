"use client";

import { ChangeEvent, useState } from "react";

type ImportRow = {
  row_number: number;
  name: string;
  pan_masked: string;
  type: string;
  dpid_masked: string;
  client_id_masked: string;
  upi_masked: string;
  account_masked: string;
  bank_name: string;
  errors: string[];
};

type ImportPreview = {
  id: string;
  status: "PREVIEWED" | "CONFIRMED";
  source_filename: string;
  row_count: number;
  error_count: number;
  rows: ImportRow[];
};

export default function AccountImport({ workspaceId, canEdit }: { workspaceId: string; canEdit: boolean }) {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setMessage("");
    setPreview(null);
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/account-imports`, { method: "POST", body });
      if (!response.ok) throw new Error("Import failed");
      const data = await response.json() as ImportPreview;
      setPreview(data);
      const validRows = data.rows.filter((row) => row.errors.length === 0).map((row) => row.row_number);
      if (validRows.length === 0) {
        setMessage("No valid rows to import. Correct the listed errors and upload again.");
        return;
      }

      try {
        const imported = await fetch(`/api/workspaces/${workspaceId}/account-imports/${data.id}`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ row_numbers: validRows }),
        });
        if (!imported.ok) {
          const result = await imported.json().catch(() => ({})) as { detail?: string };
          throw new Error(result.detail ?? "Import failed");
        }
        const result = await imported.json() as { imported_rows: number };
        setPreview({ ...data, status: "CONFIRMED" });
        const rejected = data.error_count ? ` ${data.error_count} row(s) need attention.` : "";
        setMessage(`${result.imported_rows} valid row(s) imported.${rejected} Set each bank Balance before planning.`);
      } catch (error) {
        setMessage(error instanceof Error && error.message !== "Import failed"
          ? error.message
          : "The workbook was read, but valid rows could not be imported. Upload it again to retry.");
      }
    } catch {
      setMessage("We could not read that workbook. Check the template and try again.");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  return <section className="account-import" aria-labelledby="account-import-heading">
    <h2 id="account-import-heading">Import accounts</h2>
    <p>Valid rows are imported automatically. Rows with errors are skipped. Each PAN may appear only once in a workbook. Account values are masked in this review.</p>
    {canEdit && <label className="file-picker">Choose workbook
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={busy} onChange={upload} />
    </label>}
    {preview && <>
      <p><strong>{preview.source_filename}</strong> · {preview.row_count} row(s), {preview.error_count} with errors</p>
      <div className="plan-table-wrap">
        <table className="plan-table account-import-table">
          <caption>Review import rows</caption>
          <thead><tr><th>Name</th><th>PAN</th><th>Demat</th><th>UPI</th><th>Bank account</th><th>Status</th></tr></thead>
          <tbody>{preview.rows.map((row) => <tr key={row.row_number}>
            <td data-label="Name">{row.name}</td>
            <td data-label="PAN">{row.pan_masked}</td>
            <td data-label="Demat">{row.type} · {row.dpid_masked} · {row.client_id_masked}</td>
            <td data-label="UPI">{row.upi_masked}</td>
            <td data-label="Bank account">{row.bank_name} · {row.account_masked}</td>
            <td data-label="Status">{row.errors.length ? <ul>{row.errors.map((error) => <li key={error}>{error}</li>)}</ul> : preview.status === "CONFIRMED" ? "Imported" : "Ready"}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </>}
    {message && <p role="status">{message}</p>}
  </section>;
}
