"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

export default function ThemeToggle({ className = "", initialTheme }: { className?: string; initialTheme: Theme }) {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    const onChange = (event: Event) => setTheme((event as CustomEvent<Theme>).detail);
    window.addEventListener("lotneeti-theme", onChange);
    return () => window.removeEventListener("lotneeti-theme", onChange);
  }, []);

  function selectTheme(next: Theme) {
    document.documentElement.dataset.theme = next;
    document.cookie = `lotneeti_theme=${next}; Path=/; SameSite=Lax; Max-Age=31536000${location.protocol === "https:" ? "; Secure" : ""}`;
    window.dispatchEvent(new CustomEvent<Theme>("lotneeti-theme", { detail: next }));
  }

  return <div className={`theme-toggle ${className}`} role="group" aria-label="Color theme">
    <button type="button" aria-pressed={theme === "light"} onClick={() => selectTheme("light")}><span aria-hidden="true">☀</span> Light</button>
    <button type="button" aria-pressed={theme === "dark"} onClick={() => selectTheme("dark")}><span aria-hidden="true">☾</span> Dark</button>
  </div>;
}
