"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function VerifyEmail({ token }: { token: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(token ? "" : "This verification link is invalid.");

  async function verify() {
    setBusy(true);
    try {
      const response = await fetch("/api/auth/register/verify", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (response.ok) {
        router.replace("/");
        router.refresh();
        return;
      }
      setMessage("This verification link has expired or was already used. Create your account again to get a new link.");
    } catch {
      setMessage("Verification is temporarily unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="page"><div className="shell">
    <p className="eyebrow">LotNeeti</p><h1>Verify your email</h1>
    <p className="intro">Confirm this email address to activate your account and sign in.</p>
    {token && <button type="button" onClick={verify} disabled={busy}>{busy ? "Verifying…" : "Verify email"}</button>}
    {message && <p role="status">{message}</p>}
    <p><Link href="/sign-in">Back to sign in</Link></p>
  </div></main>;
}
