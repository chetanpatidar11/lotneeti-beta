"use client";

import { useEffect, useState } from "react";

export default function ApiActivityIndicator() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const previousFetch = window.fetch;
    let pending = 0;
    let mounted = true;

    window.fetch = async (...args) => {
      const input = args[0];
      const address = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      let track = false;
      try {
        const url = new URL(address, window.location.href);
        track = url.origin === window.location.origin
          && url.pathname.startsWith("/api/")
          && url.pathname !== "/api/auth/session/refresh";
      } catch {
        // Leave non-URL requests to the browser's normal fetch handling.
      }
      if (!track) return previousFetch.call(window, ...args);

      pending += 1;
      if (pending === 1 && mounted) setVisible(true);
      try {
        return await previousFetch.call(window, ...args);
      } finally {
        pending -= 1;
        if (pending === 0 && mounted) setVisible(false);
      }
    };

    return () => {
      mounted = false;
      window.fetch = previousFetch;
    };
  }, []);

  return visible ? <div className="api-loading-indicator" role="status" aria-live="polite">
    <span className="api-loading-spinner" aria-hidden="true" />Loading…
  </div> : null;
}
