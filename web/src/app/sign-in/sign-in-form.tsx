"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { authRequestHeaders } from "@/lib/auth-request";

type Mode = "continue" | "reset";

export default function SignInForm({ linkError }: { linkError: boolean }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("continue");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState(linkError ? "That link is no longer valid. Continue with your password or reset it." : "");
  const [busy, setBusy] = useState(false);

  function changeMode(next: Mode) {
    setMode(next);
    setPassword("");
    setMessage("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const submittedEmail = String(fields.get("email") ?? "");
    const submittedPassword = String(fields.get("password") ?? "");
    setBusy(true);
    setMessage("");
    try {
      const path = mode === "continue" ? "/api/auth/password/login" : "/api/auth/password/reset/start";
      const response = await fetch(path, {
        method: "POST",
        headers: authRequestHeaders,
        body: JSON.stringify(mode === "reset"
          ? { email: submittedEmail }
          : { email: submittedEmail, password: submittedPassword }),
      });
      if (response.ok && mode === "continue") {
        router.replace("/");
        router.refresh();
        return;
      }
      if (response.ok) {
        setMessage("If this email is registered, you’ll receive a password reset link.");
      } else if (response.status === 429) {
        setMessage("Too many attempts. Please wait a minute and try again.");
      } else if (response.status === 403) {
        setMessage("This browser could not submit the form. Refresh the page and try again.");
      } else if (response.status >= 500) {
        setMessage("Account access is temporarily unavailable. Please try again.");
      } else if (mode === "continue") {
        const result = await response.json().catch(() => ({}));
        const passwordError = result.password;
        setMessage(Array.isArray(passwordError) && passwordError.length > 0
          ? passwordError[0] : "Email or password is incorrect.");
      } else {
        setMessage("Please check your email address and try again.");
      }
    } catch {
      setMessage("Account access is temporarily unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page auth-page">
      <div className="shell auth-shell">
        <p className="eyebrow">LotNeeti · IPO operations</p>
        <h1>{mode === "continue" ? "Welcome to LotNeeti" : "Reset your password"}</h1>
        <p className="intro">{mode === "continue"
          ? "Enter your email and password. We’ll open your account or create one if you’re new."
          : "Enter your email. If you have an account, we’ll send a reset link."}</p>
        <form onSubmit={submit} className="sign-in-form">
          <label htmlFor="email">Email address</label>
          <input id="email" name="email" type="email" autoComplete="email" required value={email}
            onChange={(event) => setEmail(event.target.value)} />
          {mode === "continue" && <>
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="current-password"
              minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} />
          </>}
          <button type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "continue" ? "Continue" : "Send reset link"}
          </button>
        </form>
        {message && <p className="auth-message" role="status">{message}</p>}
        <div className="auth-actions">
          {mode === "reset" && <button type="button" className="text-button" onClick={() => changeMode("continue")}>Back to account</button>}
          {mode === "continue" && <button type="button" className="text-button" onClick={() => changeMode("reset")}>Forgot password?</button>}
        </div>
      </div>
    </main>
  );
}
