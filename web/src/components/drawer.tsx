"use client";

import { useEffect, useRef, type ReactNode } from "react";

export function Drawer({ title, onClose, children, canClose = true }: { title: string; onClose: () => void; children: ReactNode; canClose?: boolean }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  function handleClose() {
    if (dialogRef.current?.open) return;
    onClose();
  }

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => { if (dialog?.open) dialog.close(); };
  }, []);
  return <dialog ref={dialogRef} className="app-drawer" aria-label={title} onCancel={(event) => { event.preventDefault(); if (canClose) onClose(); }} onClose={handleClose}>
    <div className="drawer-head"><h2>{title}</h2><button className="button-ghost" type="button" onClick={onClose} disabled={!canClose} aria-label="Close panel">×</button></div>
    <div className="drawer-body">{children}</div>
  </dialog>;
}
