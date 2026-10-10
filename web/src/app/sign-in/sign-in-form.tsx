"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type Mode = "sign-in" | "create" | "reset";

export default function SignInForm({ linkError }: { linkError: boolean }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("sign-in");
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
    if (mode === "create" && password !== confirm) {
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
        headers: { "content-type": "application/json" },
        body: JSON.stringify(mode === "reset" ? { email } : { email, password }),
      });
      if (response.ok && mode === "sign-in") {
        router.replace("/");
        router.refresh();
        return;
      }
      if (response.ok) {
        setMessage(mode === "create"
          ? "If this address can be registered, check your email once to verify it."
          : "If this account exists, check your email for a password reset link.");
      } else if (response.status === 429) {
        setMessage("Too many attempts. Please wait a minute and try again.");
      } else if (mode === "sign-in") {
        setMessage("Email or password is incorrect.");
      } else {
        const result = await response.json().catch(() => ({}));
        setMessage(Array.isArray(result.password) ? result.password[0] : "Please check your details and try again.");
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
          <input id="email" type="email" autoComplete="email" required value={email}
            onChange={(event) => setEmail(event.target.value)} />
          {mode !== "reset" && <>
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete={mode === "create" ? "new-password" : "current-password"}
              minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} />
          </>}
          {mode === "create" && <>
            <label htmlFor="confirm">Confirm password</label>
            <input id="confirm" type="password" autoComplete="new-password" minLength={8} required
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
