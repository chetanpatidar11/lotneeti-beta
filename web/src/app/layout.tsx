import type { Metadata } from "next";
import { cookies } from "next/headers";
import { backendUrl } from "@/lib/backend";
import { getCurrentUser } from "@/lib/session";
import { localPreviewEnabled } from "@/lib/local-preview";
import AppNav from "./app-nav";
import ApiActivityIndicator from "./api-activity-indicator";
import SessionKeeper from "./session-keeper";
import "./globals.css";
import "./theme.css";

export const metadata: Metadata = {
  title: "LotNeeti",
  description: "IPO planning for your family or group",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const requestCookies = await cookies();
  const cookieHeader = requestCookies.toString();
  const theme = requestCookies.get("lotneeti_theme")?.value === "dark" ? "dark" : "light";
  const signedIn = cookieHeader.includes("sessionid=");
  const user = signedIn ? await getCurrentUser() : null;
  let founderAdmin = false;
  if (user) {
    const response = await fetch(backendUrl("platform/overview/"), { headers: { cookie: cookieHeader }, cache: "no-store" }).catch(() => null);
    founderAdmin = response?.ok ?? false;
  }
  return (
    <html lang="en" data-theme={theme}>
      <head><meta name="referrer" content="no-referrer" /></head>
      <body>
        <ApiActivityIndicator />
        <a className="skip-link" href="#main-content">Skip to content</a>
        {user ? <div className="app-layout"><SessionKeeper /><AppNav email={user.email} founderAdmin={founderAdmin} theme={theme} localPreview={localPreviewEnabled() && user.email === "local-preview@lotneeti.test"} /><div className="app-main" id="main-content" tabIndex={-1}>{children}</div></div> : <div id="main-content" tabIndex={-1}>{children}</div>}
      </body>
    </html>
  );
}
