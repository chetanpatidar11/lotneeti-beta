"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authRequestHeaders } from "@/lib/auth-request";
import ThemeToggle from "../theme-toggle";

type Mode = "continue" | "verify" | "reset" | "reset-code";

export default function SignInForm({ linkError, initialTheme }: { linkError: boolean; initialTheme: "light" | "dark" }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("continue");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState(linkError ? "That link is no longer valid. Continue with your password or reset it." : "");
  const [busy, setBusy] = useState(false);

  function changeMode(next: Mode) {
    setMode(next);
    setPassword("");
    setCode("");
    setNewPassword("");
    setMessage("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedEmail = email.trim();
    const submittedPassword = password;
    setBusy(true);
    setMessage("");
    try {
      const path = mode === "continue" ? "/api/auth/password/login"
        : mode === "verify" ? "/api/auth/register/verify"
        : mode === "reset" ? "/api/auth/password/reset/start"
        : "/api/auth/password/reset/complete";
      const response = await fetch(path, {
        method: "POST",
        headers: authRequestHeaders,
        body: JSON.stringify(mode === "continue" ? { email: submittedEmail, password: submittedPassword }
          : mode === "reset" ? { email: submittedEmail }
          : mode === "verify" ? { email: submittedEmail, code }
          : { email: submittedEmail, code, password: newPassword }),
      });
      if (response.status === 202 && mode === "continue") {
        setMode("verify");
        setMessage("We sent a six-digit code to your email. Enter it within 15 minutes to finish creating your account.");
        return;
      }
      if (response.ok && (mode === "continue" || mode === "verify" || mode === "reset-code")) {
        router.replace("/");
        router.refresh();
        return;
      }
      if (response.ok) {
        setMode("reset-code");
        setMessage("If this email is registered, a six-digit reset code is on its way. Check your inbox and spam folder.");
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
      } else if (mode === "verify" || mode === "reset-code") {
        const result = await response.json().catch(() => ({}));
        setMessage(Array.isArray(result.password) ? result.password[0] : "The code is incorrect or has expired. Request a new code if needed.");
      } else {
        setMessage("Please check the email address and try again.");
      }
    } catch {
      setMessage("Account access is temporarily unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function resendCode() {
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(mode === "verify" ? "/api/auth/register" : "/api/auth/password/reset/start", {
        method: "POST", headers: authRequestHeaders,
        body: JSON.stringify(mode === "verify" ? { email, password } : { email }),
      });
      setMessage(response.ok ? "If eligible, a new code is on its way. Please allow a minute between requests."
        : "Could not send a code right now. Please try again shortly.");
    } catch {
      setMessage("Could not send a code right now. Please try again shortly.");
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
            <h1>{mode === "continue" ? "Welcome to LotNeeti" : mode === "verify" ? "Verify your email" : "Reset your password"}</h1>
            <p className="intro">{mode === "continue"
              ? "Enter your email and password. New here? We’ll email a code to verify your account."
              : mode === "verify" ? `Enter the code sent to ${email}.`
              : mode === "reset" ? "Enter your email to receive a password reset code."
              : `Enter the code sent to ${email}, then choose a new password.`}</p>
            <form onSubmit={submit} className="sign-in-form">
              <label htmlFor="email">Email address</label>
              <input id="email" name="email" type="email" autoComplete="email" placeholder="you@example.com" required value={email}
                readOnly={mode === "verify" || mode === "reset-code"}
                onChange={(event) => setEmail(event.target.value)} />
              {mode === "continue" && <>
                <label htmlFor="password">Password</label>
                <input id="password" name="password" type="password" autoComplete="current-password" placeholder="Enter your password"
                  minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} />
              </>}
              {(mode === "verify" || mode === "reset-code") && <>
                <label htmlFor="code">Six-digit email code</label>
                <input id="code" name="code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6}
                  placeholder="000000" required value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} />
              </>}
              {mode === "reset-code" && <>
                <label htmlFor="new-password">New password</label>
                <input id="new-password" name="new-password" type="password" autoComplete="new-password" minLength={8} required
                  value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
              </>}
              <button type="submit" disabled={busy}>
                {busy ? "Please wait…" : mode === "continue" ? "Continue to LotNeeti" : mode === "verify" ? "Verify and continue" : mode === "reset" ? "Send reset code" : "Reset password"}
              </button>
            </form>
            {message && <p className="auth-message" role="status">{message}</p>}
            <div className="auth-actions">
              {mode !== "continue" && <button type="button" className="text-button" onClick={() => changeMode("continue")}>← Back to account</button>}
              {mode === "continue" && <button type="button" className="text-button" onClick={() => changeMode("reset")}>Forgot password?</button>}
              {(mode === "verify" || mode === "reset-code") && <button type="button" className="text-button" disabled={busy} onClick={() => void resendCode()}>Send code again</button>}
            </div>
          </div>
          <p className="auth-panel-foot">One account for your IPO planning workspace.</p>
        </section>
      </div>
    </main>
  );
}
