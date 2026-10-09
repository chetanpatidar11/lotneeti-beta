"use client";

import { FormEvent, useState } from "react";

export default function SignInForm({ linkError }: { linkError: boolean }) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState(linkError ? "That sign-in link is no longer valid." : "");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const response = await fetch("/api/auth/email/start", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email }),
      });
      setMessage(
        response.ok
          ? "If this address can sign in, check your email for a link."
          : "We could not send a link right now. Please try again.",
      );
    } catch {
      setMessage("We could not send a link right now. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <div className="shell">
        <p className="eyebrow">LotNeeti</p>
        <h1>Sign in</h1>
        <p className="intro">Enter your email address and we’ll send you a sign-in link.</p>
        <form onSubmit={submit} className="sign-in-form">
          <label htmlFor="email">Email address</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button type="submit" disabled={busy}>
            {busy ? "Sending…" : "Send sign-in link"}
          </button>
        </form>
        {message && <p role="status">{message}</p>}
      </div>
    </main>
  );
}
