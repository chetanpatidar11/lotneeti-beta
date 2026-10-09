import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "@/lib/backend";
import { selectedWorkspace } from "@/lib/workspace";
import PortfolioScreen, { type AllottedApplication, type ProfitReport, type SaleItem } from "./portfolio-screen";

type Workspace = { id: string; role: string };

export default async function PortfolioPage({ searchParams }: { searchParams: Promise<{ from_date?: string; to_date?: string }> }) {
  const period = await searchParams;
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) redirect("/sign-in");
  const headers = { cookie: cookieHeader };
  const workspacesResponse = await fetch(backendUrl("workspaces/"), { headers, cache: "no-store" });
  if (!workspacesResponse.ok) redirect("/sign-in");
  const workspace = await selectedWorkspace((await workspacesResponse.json()) as Workspace[]);
  if (!workspace) redirect("/settings/investors");
  const reportQuery = new URLSearchParams();
  if (period.from_date) reportQuery.set("from_date", period.from_date);
  if (period.to_date) reportQuery.set("to_date", period.to_date);
  const [applicationsResponse, salesResponse, reportResponse] = await Promise.all([
    fetch(backendUrl(`workspaces/${workspace.id}/applications/`), { headers, cache: "no-store" }),
    fetch(backendUrl(`workspaces/${workspace.id}/sales/`), { headers, cache: "no-store" }),
    fetch(backendUrl(`workspaces/${workspace.id}/pnl/${reportQuery.size ? `?${reportQuery}` : ""}`), { headers, cache: "no-store" }),
  ]);
  const applications = applicationsResponse.ok ? ((await applicationsResponse.json()) as AllottedApplication[]) : [];
  const sales = salesResponse.ok ? ((await salesResponse.json()) as SaleItem[]) : [];
  const report = reportResponse.ok ? ((await reportResponse.json()) as ProfitReport) : null;
  return <PortfolioScreen workspaceId={workspace.id} canEdit={workspace.role !== "VIEWER"} initialApplications={applications} initialSales={sales} report={report} fromDate={period.from_date ?? ""} toDate={period.to_date ?? ""} initialLoadError={!applicationsResponse.ok || !salesResponse.ok} />;
}
