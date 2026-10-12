"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authRequestHeaders } from "@/lib/auth-request";
import ThemeToggle from "../theme-toggle";

type Mode = "continue" | "reset";

export default function SignInForm({ linkError, initialTheme }: { linkError: boolean; initialTheme: "light" | "dark" }) {
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
      <div className="auth-layout">
        <section className="auth-story" aria-label="About LotNeeti">
          <Link className="auth-brand" href="/"><span className="auth-brand-mark" aria-hidden="true">L</span><span>Lot<span>Neeti</span><small>IPO OPERATIONS</small></span></Link>
          <div className="auth-story-copy">
            <p className="auth-kicker">A clearer way to plan</p>
            <h2>Every IPO decision, <em>in one clear place.</em></h2>
            <p className="auth-story-intro">Bring your applicants, accounts and plans together. See what needs attention before you apply.</p>
            <div className="auth-feature-list">
              <div><span aria-hidden="true">01</span><p><strong>Discover issues</strong><small>Review open and upcoming IPOs with the facts that matter.</small></p></div>
              <div><span aria-hidden="true">02</span><p><strong>Plan with confidence</strong><small>Match applicants with demat, bank and UPI accounts.</small></p></div>
              <div><span aria-hidden="true">03</span><p><strong>Stay on top</strong><small>Follow funds, applications and allotments in one workspace.</small></p></div>
            </div>
          </div>
          <p className="auth-story-foot">Built for thoughtful IPO planning.</p>
        </section>
        <section className="shell auth-shell" aria-label="Account access">
          <div className="auth-panel-top"><span className="auth-panel-brand">LotNeeti</span><ThemeToggle initialTheme={initialTheme} /></div>
          <div className="auth-form-content">
            <p className="eyebrow">Your workspace awaits</p>
            <h1>{mode === "continue" ? "Welcome to LotNeeti" : "Reset your password"}</h1>
            <p className="intro">{mode === "continue"
              ? "Enter your email and password. New here? We’ll create your account with the same details."
              : "Enter your email. If you have an account, we’ll send a reset link."}</p>
            <form onSubmit={submit} className="sign-in-form">
              <label htmlFor="email">Email address</label>
              <input id="email" name="email" type="email" autoComplete="email" placeholder="you@example.com" required value={email}
                onChange={(event) => setEmail(event.target.value)} />
              {mode === "continue" && <>
                <label htmlFor="password">Password</label>
                <input id="password" name="password" type="password" autoComplete="current-password" placeholder="Enter your password"
                  minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} />
              </>}
              <button type="submit" disabled={busy}>
                {busy ? "Please wait…" : mode === "continue" ? "Continue to LotNeeti" : "Send reset link"}
              </button>
            </form>
            {message && <p className="auth-message" role="status">{message}</p>}
            <div className="auth-actions">
              {mode === "reset" && <button type="button" className="text-button" onClick={() => changeMode("continue")}>← Back to account</button>}
              {mode === "continue" && <button type="button" className="text-button" onClick={() => changeMode("reset")}>Forgot password?</button>}
            </div>
          </div>
          <p className="auth-panel-foot">One account for your IPO planning workspace.</p>
        </section>
      </div>
    </main>
  );
}
