"use client";

import { useState } from "react";

export default function SignOutButton() {
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    const response = await fetch("/api/auth/logout", { method: "POST" });
    if (response.ok) {
      window.location.reload();
    } else {
      setBusy(false);
    }
  }

  return <button onClick={signOut} disabled={busy}>{busy ? "Signing out…" : "Sign out"}</button>;
}
