import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "@/lib/backend";
import { selectedWorkspace } from "@/lib/workspace";
import ApplicationsScreen, { type ApplicationItem } from "./applications-screen";

type Workspace = { id: string; role: string };
type LatestRun = { id: string | null; status: "READY" | "BLOCKED" | null };

export default async function ApplicationsPage() {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) redirect("/sign-in");
  const headers = { cookie: cookieHeader };
  const workspacesResponse = await fetch(backendUrl("workspaces/"), { headers, cache: "no-store" });
  if (!workspacesResponse.ok) redirect("/sign-in");
  const workspace = await selectedWorkspace((await workspacesResponse.json()) as Workspace[]);
  if (!workspace) redirect("/settings/investors");
  const [itemsResponse, runResponse] = await Promise.all([
    fetch(backendUrl(`workspaces/${workspace.id}/applications/`), { headers, cache: "no-store" }),
    fetch(backendUrl(`workspaces/${workspace.id}/planner/runs/latest/`), { headers, cache: "no-store" }),
  ]);
  const items = itemsResponse.ok ? ((await itemsResponse.json()) as ApplicationItem[]) : [];
  const latest = runResponse.ok ? ((await runResponse.json()) as LatestRun) : { id: null, status: null };
  return <ApplicationsScreen workspaceId={workspace.id} canEdit={workspace.role !== "VIEWER"} initialItems={items} latestRun={latest} initialLoadError={!itemsResponse.ok || !runResponse.ok} />;
}
