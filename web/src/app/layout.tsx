import type { Metadata } from "next";
import { cookies } from "next/headers";
import { backendUrl } from "@/lib/backend";
import { getCurrentUser } from "@/lib/session";
import { localPreviewEnabled } from "@/lib/local-preview";
import { selectedWorkspace } from "@/lib/workspace";
import AppNav from "./app-nav";
import "./globals.css";
import "./theme.css";

export const metadata: Metadata = {
  title: "LotNeeti",
  description: "IPO planning for your family or group",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const cookieHeader = (await cookies()).toString();
  const signedIn = cookieHeader.includes("sessionid=");
  const user = signedIn ? await getCurrentUser() : null;
  let workspaces: { id: string; name: string; role: string }[] = [];
  let founderAdmin = false;
  if (user) {
    const headers = { cookie: cookieHeader };
    const [workspaceResponse, founderResponse] = await Promise.allSettled([
      fetch(backendUrl("workspaces/"), { headers, cache: "no-store" }),
      fetch(backendUrl("platform/overview/"), { headers, cache: "no-store" }),
    ]);
    if (workspaceResponse.status === "fulfilled" && workspaceResponse.value.ok) {
      workspaces = await workspaceResponse.value.json() as typeof workspaces;
    }
    founderAdmin = founderResponse.status === "fulfilled" && founderResponse.value.ok;
  }
  const workspace = await selectedWorkspace(workspaces);
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">Skip to content</a>
        {user ? <div className="app-layout"><AppNav email={user.email} workspaces={workspaces} selectedId={workspace?.id} founderAdmin={founderAdmin} localPreview={localPreviewEnabled() && user.email === "local-preview@lotneeti.test"} /><div className="app-main" id="main-content" tabIndex={-1}>{children}</div></div> : <div id="main-content" tabIndex={-1}>{children}</div>}
      </body>
    </html>
  );
}
