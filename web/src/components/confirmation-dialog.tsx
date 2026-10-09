"use client";

import { useEffect, useRef } from "react";

export function ConfirmationDialog({
  title,
  description,
  confirmLabel,
  busy,
  onConfirm,
  onCancel,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => { if (dialog?.open) dialog.close(); };
  }, []);
  return <dialog ref={dialogRef} className="confirmation-dialog" aria-label={title} onCancel={(event) => { if (busy) event.preventDefault(); else onCancel(); }}>
    <h2>{title}</h2>
    <p>{description}</p>
    <div className="confirmation-actions">
      <button type="button" className="button-secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      <button type="button" className="button-danger" disabled={busy} onClick={onConfirm}>{busy ? "Deleting…" : confirmLabel}</button>
    </div>
  </dialog>;
}
