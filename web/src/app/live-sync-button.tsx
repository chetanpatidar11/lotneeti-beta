"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AUTH_REQUEST_HEADER } from "@/lib/auth-request";

export default function LiveSyncButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refresh() {
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/ipos/live-sync", {
        method: "POST",
        headers: { "content-type": "application/json", [AUTH_REQUEST_HEADER]: "1" },
        body: "{}",
      });
      const data = await response.json();
      if (response.ok && data.result?.status === "OK") {
        setMessage(`Updated from InvestorGain. ${data.result.imported ?? 0} new IPOs; ${data.result.created ?? 0} new GMP observations.`);
        router.refresh();
      } else if (response.status === 429) {
        setMessage("A refresh just ran. Please wait five minutes before trying again.");
      } else {
        setMessage("Live sync could not finish. Please try again later.");
      }
    } catch {
      setMessage("Live sync is unavailable right now. Please try again later.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="live-sync-control"><button type="button" onClick={refresh} disabled={busy}>{busy ? "Syncing…" : "Live sync"}</button>{message && <span role="status">{message}</span>}</div>;
}
