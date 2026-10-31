import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "@/lib/backend";
import { selectedWorkspace } from "@/lib/workspace";
import type { ApplicationItem } from "../applications/applications-screen";
import CheckAllotmentScreen from "./check-allotment-screen";

type Workspace = { id: string; role: string };

export default async function CheckAllotmentPage() {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) redirect("/sign-in");
  const headers = { cookie: cookieHeader };
  const workspacesResponse = await fetch(backendUrl("workspaces/"), { headers, cache: "no-store" });
  if (!workspacesResponse.ok) redirect("/sign-in");
  const workspace = await selectedWorkspace((await workspacesResponse.json()) as Workspace[]);
  if (!workspace) redirect("/settings/investors");
  const response = await fetch(backendUrl(`workspaces/${workspace.id}/applications/`), { headers, cache: "no-store" });
  const items = response.ok ? await response.json() as ApplicationItem[] : [];
  return <CheckAllotmentScreen workspaceId={workspace.id} canEdit={workspace.role !== "VIEWER"} initialItems={items} initialLoadError={!response.ok} />;
}
