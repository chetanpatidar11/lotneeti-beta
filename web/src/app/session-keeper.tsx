"use client";

import { useEffect } from "react";

export default function SessionKeeper() {
  useEffect(() => {
    void fetch("/api/auth/session/refresh", { method: "POST", cache: "no-store" });
  }, []);
  return null;
}
