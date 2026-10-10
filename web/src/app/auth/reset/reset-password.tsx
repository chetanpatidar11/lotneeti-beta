"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

export default function ResetPassword({ token }: { token: string }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(token ? "" : "This reset link is invalid.");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password !== confirm) {
      setMessage("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/auth/password/reset/complete", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      if (response.ok) {
        router.replace("/");
        router.refresh();
        return;
      }
      const result = await response.json().catch(() => ({}));
      setMessage(Array.isArray(result.password) ? result.password[0] : "This reset link has expired or was already used.");
    } catch {
      setMessage("Password reset is temporarily unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="page"><div className="shell">
    <p className="eyebrow">LotNeeti</p><h1>Choose a new password</h1>
    {token && <form onSubmit={submit} className="sign-in-form">
      <label htmlFor="password">New password</label>
      <input id="password" type="password" autoComplete="new-password" minLength={8} required
        value={password} onChange={(event) => setPassword(event.target.value)} />
      <label htmlFor="confirm">Confirm password</label>
      <input id="confirm" type="password" autoComplete="new-password" minLength={8} required
        value={confirm} onChange={(event) => setConfirm(event.target.value)} />
      <button type="submit" disabled={busy}>{busy ? "Saving…" : "Save password"}</button>
    </form>}
    {message && <p role="status">{message}</p>}
    <p><Link href="/sign-in">Back to sign in</Link></p>
  </div></main>;
}
