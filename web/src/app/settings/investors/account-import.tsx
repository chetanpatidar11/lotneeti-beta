"use client";

import { ChangeEvent, FormEvent, PointerEvent, useRef, useState } from "react";
import { emptyImageRow, ImageImportRow, importFields, rowsFromImageTsv } from "./image-ocr";

type ImportRow = {
  row_number: number; name: string; pan_masked: string; pan_display: string; type: string;
  dpid_masked: string; dpid_display?: string; client_id_masked: string; client_id_display: string; upi_id: string;
  account_masked: string; account_display?: string; bank_name: string; payment_reference: string;
  payment_pending: boolean; shared_upi: boolean; using_upi_as_account: boolean; errors: string[];
};
type ImportPreview = {
  id: string; status: "PREVIEWED" | "CONFIRMED"; source_filename: string;
  row_count: number; error_count: number; rows: ImportRow[];
};
type ExistingInvestor = { id: string; name: string; pan_masked: string; pan_display: string; active: boolean };
const selectable = (row: ImportRow) => row.errors.length === 0;
const initialColumnWidths = [76, 240, 130, 220, 250, 250, 140];
const columnLabels = ["Import", "Name", "PAN", "Demat", "UPI", "Bank details", "Status"];

export default function AccountImport({ workspaceId, canEdit, investors }: { workspaceId: string; canEdit: boolean; investors: ExistingInvestor[] }) {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [upiOwners, setUpiOwners] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [imageRows, setImageRows] = useState<ImageImportRow[] | null>(null);
  const [imageName, setImageName] = useState("");
  const [ocrProgress, setOcrProgress] = useState("");
  const [columnWidths, setColumnWidths] = useState(initialColumnWidths);
  const resize = useRef<{ index: number; startX: number; startWidth: number } | null>(null);

  function startResize(event: PointerEvent<HTMLSpanElement>, index: number) {
    resize.current = { index, startX: event.clientX, startWidth: columnWidths[index] };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveResize(event: PointerEvent<HTMLSpanElement>) {
    if (!resize.current) return;
    const { index, startX, startWidth } = resize.current;
    setColumnWidths((current) => current.map((width, position) =>
      position === index ? Math.max(72, startWidth + event.clientX - startX) : width,
    ));
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true); setMessage(""); setPreview(null); setUpiOwners({}); setImageRows(null); setImageName("");
    if (/\.(png|jpe?g|webp)$/i.test(file.name)) {
      try {
        if (file.size > 10 * 1024 * 1024) throw new Error("Choose an image smaller than 10 MB.");
        setOcrProgress("Reading image on this device…");
        const { createWorker } = await import("tesseract.js");
        const worker = await createWorker("eng", 1, {
          workerPath: "/ocr/worker.min.js",
          corePath: "/ocr/tesseract-core-lstm.wasm.js",
          langPath: "/ocr",
          logger: (progress) => {
            if (progress.status === "recognizing text") {
              setOcrProgress(`Reading image… ${Math.round(progress.progress * 100)}%`);
            }
          },
        });
        try {
          const result = await worker.recognize(file, {}, { tsv: true });
          const rows = rowsFromImageTsv(result.data.tsv ?? "");
          setImageRows(rows.length ? rows : [emptyImageRow()]);
          setImageName(file.name);
          setMessage(rows.length
            ? "Check every extracted field below. Image text can be misread; correct it before importing."
            : "No complete row was found. Enter the details from the image below, then review the import.");
        } finally { await worker.terminate(); }
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "The image could not be read.");
      } finally { setBusy(false); setOcrProgress(""); event.target.value = ""; }
      return;
    }
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

  async function reviewImage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!imageRows?.length || !imageName) return;
    setBusy(true); setMessage("");
    const body = new FormData();
    body.append("source_filename", imageName);
    body.append("image_rows", JSON.stringify(imageRows));
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/account-imports`, { method: "POST", body });
      if (!response.ok) {
        const result = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(result.detail ?? "The image rows could not be reviewed.");
      }
      const data = await response.json() as ImportPreview;
      setPreview(data);
      if (data.error_count === 0) setImageRows(null);
      setSelected(data.rows.filter(selectable).map((row) => row.row_number));
      if (data.error_count > 0) setMessage("Some extracted details need correction. Edit the rows above and review again, or import only the ready rows below.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The image rows could not be reviewed.");
    } finally { setBusy(false); }
  }

  function updateImageRow(index: number, field: keyof ImageImportRow, value: string) {
    setPreview(null);
    setImageRows((current) => current?.map((row, position) =>
      position === index ? { ...row, [field]: value } : row) ?? null);
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preview || selected.length === 0) return;
    const grouped = Object.groupBy(preview.rows.filter((row) => selected.includes(row.row_number)), (row) => row.upi_id);
    const missingOwner = Object.entries(grouped).some(([upi, rows]) => !ownerChoice(upi, rows ?? []));
    if (missingOwner) { setMessage("Choose the bank account owner for each UPI ID."); return; }
    setBusy(true); setMessage("");
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/account-imports/${preview.id}`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ row_numbers: selected, shared_upi_owners: Object.fromEntries(Object.entries(grouped).map(([upi, rows]) => [upi, ownerChoice(upi, rows ?? [])])) }),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => ({})) as { detail?: string; errors?: Record<string, string[]> };
        const rowErrors = Object.entries(result.errors ?? {}).map(([row, errors]) => `Row ${row}: ${errors.join(" ")}`).join(" ");
        throw new Error(rowErrors || result.detail || "The selected rows could not be imported.");
      }
      const result = await response.json() as { imported_rows: number; created: { banks: number; upis: number; payment_pending: number } };
      try {
        sessionStorage.setItem(`lotneeti-import-success:${workspaceId}`, `${result.imported_rows} investor(s), ${result.created.upis} UPI ID(s) and ${result.created.banks} bank account(s) imported.`);
      } catch { /* Import succeeded; storage may be unavailable in private browsing. */ }
      window.location.reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The selected rows could not be imported.");
    } finally { setBusy(false); }
  }

  const selectedGroups = Object.groupBy(preview?.rows.filter((row) => selected.includes(row.row_number)) ?? [], (row) => row.upi_id);
  const ownerGroups = Object.entries(selectedGroups);

  function ownerChoice(upi: string, rows: ImportRow[]): string {
    const chosen = upiOwners[upi];
    if (chosen?.startsWith("row:") && !selected.includes(Number(chosen.slice(4)))) return "";
    return chosen ?? (rows.length === 1 ? `row:${rows[0].row_number}` : "");
  }

  return <section className="account-import" aria-labelledby="account-import-heading">
    <h2 id="account-import-heading">Import accounts</h2>
    <p>Upload an Excel file or a clear table image to set up investors, demats, UPIs and active bank accounts. Account Number and Bank Name columns are optional. Missing details default to BANK with the UPI ID as the account number. Every account starts with ₹0 Balance.</p>
    {canEdit && <label className="file-picker">Choose Excel file or image
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" disabled={busy} onChange={upload} />
    </label>}
    {ocrProgress && <p role="status">{ocrProgress}</p>}
    {imageRows && <form onSubmit={reviewImage} className="image-import-review">
      <h3>Check details from {imageName}</h3>
      <p>The image stays on your device. Check PAN, client ID and UPI carefully before continuing.</p>
      <div className="plan-table-wrap"><table className="plan-table image-import-table">
        <caption>Extracted image rows</caption>
        <thead><tr>{importFields.map((field) => <th key={field} scope="col">{field}</th>)}<th scope="col">Remove</th></tr></thead>
        <tbody>{imageRows.map((row, index) => <tr key={index}>
          {importFields.map((field) => <td key={field}><input aria-label={`${field} for row ${index + 1}`} value={row[field]} disabled={busy} onChange={(event) => updateImageRow(index, field, event.target.value)} /></td>)}
          <td><button type="button" disabled={busy || imageRows.length === 1} onClick={() => { setPreview(null); setImageRows((current) => current?.filter((_, position) => position !== index) ?? null); }}>Remove</button></td>
        </tr>)}</tbody>
      </table></div>
      <div className="form-actions"><button type="button" disabled={busy || imageRows.length >= 100} onClick={() => { setPreview(null); setImageRows((current) => [...(current ?? []), emptyImageRow()]); }}>+ Add row</button><button type="submit" disabled={busy}>Review import rows</button></div>
    </form>}
    {preview && <form onSubmit={confirm}>
      <p><strong>{preview.source_filename}</strong> · {preview.row_count} row(s), {preview.error_count} with errors</p>
      <div className="plan-table-wrap"><table className="plan-table account-import-table" style={{ width: columnWidths.reduce((total, width) => total + width, 0) }}>
        <caption>Review import rows</caption>
        <colgroup>{columnWidths.map((width, index) => <col key={columnLabels[index]} style={{ width }} />)}</colgroup>
        <thead><tr>{columnLabels.map((label, index) => <th key={label} scope="col">{label}<span className="import-column-resizer" role="separator" tabIndex={0} aria-label={`Resize ${label} column`} aria-orientation="vertical" onPointerDown={(event) => startResize(event, index)} onPointerMove={moveResize} onPointerUp={() => { resize.current = null; }} onPointerCancel={() => { resize.current = null; }} onKeyDown={(event) => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); setColumnWidths((current) => current.map((width, position) => position === index ? Math.max(72, width + (event.key === "ArrowRight" ? 24 : -24)) : width)); } }} /></th>)}</tr></thead>
        <tbody>{preview.rows.map((row) => {
          const checked = selected.includes(row.row_number);
          const canSelect = selectable(row);
          return <tr key={row.row_number}>
            <td data-label="Import"><input type="checkbox" aria-label={`Import row ${row.row_number} for ${row.name}`} checked={checked} disabled={!canEdit || busy || !canSelect || preview.status === "CONFIRMED"} onChange={(event) => setSelected((current) => event.target.checked ? [...current, row.row_number] : current.filter((number) => number !== row.row_number))} /></td>
            <td data-label="Name" title={row.name}>{row.name}</td><td data-label="PAN">{row.pan_display}</td>
            <td data-label="Demat" title={`${row.type} · ${row.dpid_display ?? row.dpid_masked} · ${row.client_id_display}`}>{row.type} · {row.dpid_display ?? row.dpid_masked} · {row.client_id_display}</td>
            <td data-label="UPI" title={row.upi_id}>{row.upi_id}</td>
            <td data-label="Bank details"><span>{row.bank_name} · {row.account_display ?? row.account_masked}</span></td>
            <td data-label="Status">{preview.status === "CONFIRMED" && checked ? "Imported" : canSelect ? checked && !ownerChoice(row.upi_id, selectedGroups[row.upi_id] ?? []) ? "Choose owner" : "Ready" : <details className="import-row-errors"><summary>{row.errors.length} {row.errors.length === 1 ? "issue" : "issues"}</summary><ul>{row.errors.map((error) => <li key={error}>{error}</li>)}</ul></details>}</td>
          </tr>;
        })}</tbody>
      </table></div>
      {ownerGroups.length > 0 && <div className="account-import-shared"><h3>Bank account owners</h3><p>Choose from any selected investor in this workbook or an active investor already in your workspace. The same person can own more than one UPI. A UPI used by one row defaults to that investor.</p>{ownerGroups.map(([upi, rows]) => <label key={upi} htmlFor={`upi-owner-${rows?.[0]?.row_number}`}>{upi}<select id={`upi-owner-${rows?.[0]?.row_number}`} value={ownerChoice(upi, rows ?? [])} disabled={!canEdit || busy || preview.status === "CONFIRMED"} onChange={(event) => setUpiOwners((current) => ({ ...current, [upi]: event.target.value }))} required><option value="">Choose bank account owner</option><optgroup label="Investors in this import">{preview.rows.filter((row) => selected.includes(row.row_number)).map((row) => <option key={row.row_number} value={`row:${row.row_number}`}>{row.name}</option>)}</optgroup>{investors.some((investor) => investor.active) && <optgroup label="Already in this workspace">{investors.filter((investor) => investor.active).map((investor) => <option key={investor.id} value={`investor:${investor.id}`}>{investor.name} · {investor.pan_display}</option>)}</optgroup>}</select></label>)}</div>}
      {canEdit && preview.status === "PREVIEWED" && <button type="submit" disabled={busy || selected.length === 0}>Import selected ({selected.length})</button>}
    </form>}
    {message && <p role="status">{message}</p>}
  </section>;
}
