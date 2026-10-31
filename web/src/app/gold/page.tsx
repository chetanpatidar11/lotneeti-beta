import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "@/lib/backend";
import { selectedWorkspace } from "@/lib/workspace";
import type { GoldReport } from "@/lib/gold";
import GoldScreen from "./gold-screen";

type Workspace = { id: string; role: string };

export default async function GoldPage() {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) redirect("/sign-in");
  const headers = { cookie: cookieHeader };
  const workspacesResponse = await fetch(backendUrl("workspaces/"), { headers, cache: "no-store" });
  if (!workspacesResponse.ok) redirect("/sign-in");
  const workspace = await selectedWorkspace((await workspacesResponse.json()) as Workspace[]);
  if (!workspace) redirect("/settings/investors");
  let report: GoldReport | null = null;
  try {
    const response = await fetch(backendUrl(`workspaces/${workspace.id}/gold/`), { headers, cache: "no-store" });
    if (response.ok) report = await response.json() as GoldReport;
  } catch { /* The screen provides an explicit retry instead of showing false zero balances. */ }
  return <GoldScreen workspaceId={workspace.id} canEdit={workspace.role !== "VIEWER"} initialReport={report} />;
}
