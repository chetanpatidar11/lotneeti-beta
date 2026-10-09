"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="page"><div className="shell"><div className="plan-error" role="alert"><strong>This page could not be loaded.</strong><p>Try again. If the problem continues, check that the local API is running.</p><button type="button" onClick={reset}>Retry</button></div></div></main>;
}
