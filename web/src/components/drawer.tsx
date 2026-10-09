"use client";

import { useEffect, useRef, type ReactNode } from "react";

export function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
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
  return <dialog ref={dialogRef} className="app-drawer" aria-label={title} onCancel={onClose} onClose={handleClose}>
    <div className="drawer-head"><h2>{title}</h2><button className="button-ghost" type="button" onClick={onClose} aria-label="Close panel">×</button></div>
    <div className="drawer-body">{children}</div>
  </dialog>;
}
