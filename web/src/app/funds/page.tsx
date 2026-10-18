import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "@/lib/backend";
import { selectedWorkspace } from "@/lib/workspace";
import FundsScreen from "./funds-screen";
import type { ScheduledPayment } from "./scheduled-payments";

type Workspace = { id: string; name: string; role: string };
type Investor = { id: string; name: string; active: boolean };
type Bank = {
  id: string;
  owner: string;
  bank_name: string;
  account_masked: string;
  account_reference: string;
  account_display: string;
  current_balance: string;
  active: boolean;
};
type CapitalLine = { balance: string; blocked: string; planned: string; available: string };
type ArchivedBank = { id: string; bank_name: string; account_masked: string; last_changed: string };

async function getData(path: string, cookieHeader: string) {
  return fetch(backendUrl(path), { headers: { cookie: cookieHeader }, cache: "no-store" });
}

export default async function FundsPage() {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) redirect("/sign-in");
  const workspaceResponse = await getData("workspaces/", cookieHeader);
  if (!workspaceResponse.ok) redirect("/sign-in");
  const workspaces = (await workspaceResponse.json()) as Workspace[];
  const workspace = await selectedWorkspace(workspaces);
  if (!workspace) redirect("/settings/investors");

  const [banksResponse, investorsResponse, capitalResponse, archiveResponse] = await Promise.all([
    getData(`workspaces/${workspace.id}/banks/`, cookieHeader),
    getData(`workspaces/${workspace.id}/investors/`, cookieHeader),
    getData(`workspaces/${workspace.id}/capital/`, cookieHeader),
    getData(`workspaces/${workspace.id}/banks/archived-history/`, cookieHeader),
  ]);
  const allBanks = banksResponse.ok ? ((await banksResponse.json()) as Bank[]) : [];
  const investors = investorsResponse.ok ? ((await investorsResponse.json()) as Investor[]).filter((item) => item.active) : [];
  const banks = allBanks.filter((bank) => bank.active && investors.some((investor) => investor.id === bank.owner));
  const capital = capitalResponse.ok ? (await capitalResponse.json()) as { by_bank?: Record<string, CapitalLine> } : null;
  const archivedBanks = archiveResponse.ok ? (await archiveResponse.json()) as ArchivedBank[] : [];
  let payments: ScheduledPayment[] = [];
  if (banks[0]) {
    const paymentsResponse = await getData(`workspaces/${workspace.id}/banks/${banks[0].id}/recurring-debits/`, cookieHeader);
    if (paymentsResponse.ok) payments = (await paymentsResponse.json()) as ScheduledPayment[];
  }

  return <FundsScreen workspace={workspace} investors={investors} initialBanks={banks} statementBanks={allBanks} initialPayments={payments} capitalByBank={capital?.by_bank ?? {}} archivedBanks={archivedBanks} />;
}
