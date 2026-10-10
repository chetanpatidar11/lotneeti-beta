"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { authRequestHeaders } from "@/lib/auth-request";

type Mode = "sign-in" | "create" | "reset";

export default function SignInForm({ linkError, initialMode = "sign-in" }: { linkError: boolean; initialMode?: "sign-in" | "create" }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState(linkError ? "That verification link is no longer valid." : "");
  const [busy, setBusy] = useState(false);

  function changeMode(next: Mode) {
    setMode(next);
    setPassword("");
    setConfirm("");
    setMessage("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const submittedEmail = String(fields.get("email") ?? "");
    const submittedPassword = String(fields.get("password") ?? "");
    const submittedConfirm = String(fields.get("confirm") ?? "");
    if (mode === "create" && submittedPassword !== submittedConfirm) {
      setMessage("Passwords do not match.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const path = mode === "sign-in"
        ? "/api/auth/password/login"
        : mode === "create" ? "/api/auth/register" : "/api/auth/password/reset/start";
      const response = await fetch(path, {
        method: "POST",
        headers: authRequestHeaders,
        body: JSON.stringify(mode === "reset"
          ? { email: submittedEmail }
          : { email: submittedEmail, password: submittedPassword }),
      });
      if (response.ok && mode === "sign-in") {
        router.replace("/");
        router.refresh();
        return;
      }
      if (response.ok) {
        setMessage(mode === "create"
          ? "If this address needs verification, check your email. Already verified? Sign in."
          : "If this account exists, check your email for a password reset link.");
      } else if (response.status === 429) {
        setMessage("Too many attempts. Please wait a minute and try again.");
      } else if (response.status === 403) {
        setMessage("This browser could not submit the form. Refresh the page and try again.");
      } else if (response.status >= 500) {
        setMessage("Sign-in is temporarily unavailable. Please try again.");
      } else if (mode === "sign-in") {
        setMessage("Email or password is incorrect.");
      } else {
        const result = await response.json().catch(() => ({}));
        const fieldError = ["email", "password", "confirm"]
          .map((field) => result[field])
          .find((value) => Array.isArray(value) && value.length > 0);
        setMessage(fieldError?.[0] ?? "Please check your details and try again.");
      }
    } catch {
      setMessage("Sign-in is temporarily unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <div className="shell">
        <p className="eyebrow">LotNeeti</p>
        <h1>{mode === "sign-in" ? "Sign in" : mode === "create" ? "Create account" : "Reset password"}</h1>
        <p className="intro">{mode === "sign-in"
          ? "Use your email and password to continue. Your session lasts up to 30 days."
          : mode === "create"
            ? "Verify your email once. Then sign in with your password."
            : "We’ll send a one-time reset link to your email."}</p>
        <form onSubmit={submit} className="sign-in-form">
          <label htmlFor="email">Email address</label>
          <input id="email" name="email" type="email" autoComplete="email" required value={email}
            onChange={(event) => setEmail(event.target.value)} />
          {mode !== "reset" && <>
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete={mode === "create" ? "new-password" : "current-password"}
              minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} />
          </>}
          {mode === "create" && <>
            <label htmlFor="confirm">Confirm password</label>
            <input id="confirm" name="confirm" type="password" autoComplete="new-password" minLength={8} required
              value={confirm} onChange={(event) => setConfirm(event.target.value)} />
          </>}
          <button type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "sign-in" ? "Sign in" : mode === "create" ? "Create account" : "Send reset link"}
          </button>
        </form>
        {message && <p role="status">{message}</p>}
        <div className="auth-actions">
          {mode !== "sign-in" && <button type="button" className="text-button" onClick={() => changeMode("sign-in")}>Back to sign in</button>}
          {mode !== "create" && <button type="button" className="text-button" onClick={() => changeMode("create")}>Create an account</button>}
          {mode !== "reset" && <button type="button" className="text-button" onClick={() => changeMode("reset")}>Forgot password?</button>}
        </div>
      </div>
    </main>
  );
}
