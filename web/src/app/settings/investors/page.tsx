import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "@/lib/backend";
import { selectedWorkspace } from "@/lib/workspace";
import PrioritySettings from "./priority-settings";
import type { BankOption, FundingPreference } from "./preferred-funding";

type Workspace = { id: string; name: string; role: string };
type Investor = {
  id: string;
  name: string;
  pan_masked: string;
  planning_priority: number;
  active: boolean;
};
type Demat = { id: string; depository: string; dp_id_masked: string; client_id_masked: string; broker: string; active: boolean };
type Upi = { id: string; holder: string; bank_id: string; handle_masked: string; active: boolean; verified: boolean };
type LinkedAccounts = Record<string, { demats: Demat[]; upis: Upi[] }>;

async function getData(path: string, cookieHeader: string) {
  return fetch(backendUrl(path), { headers: { cookie: cookieHeader }, cache: "no-store" });
}

export default async function InvestorSettingsPage() {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) redirect("/sign-in");
  const workspaceResponse = await getData("workspaces/", cookieHeader);
  if (!workspaceResponse.ok) redirect("/sign-in");
  const workspaces = (await workspaceResponse.json()) as Workspace[];
  const workspace = await selectedWorkspace(workspaces);
  let investors: Investor[] = [];
  let banks: BankOption[] = [];
  const preferences: Record<string, FundingPreference[]> = {};
  const linkedAccounts: LinkedAccounts = {};
  let loadError = false;
  if (workspace) {
    const [investorsResponse, banksResponse] = await Promise.all([
      getData(`workspaces/${workspace.id}/investors/`, cookieHeader),
      getData(`workspaces/${workspace.id}/banks/`, cookieHeader),
    ]);
    if (investorsResponse.ok) investors = (await investorsResponse.json()) as Investor[];
    else loadError = true;
    if (banksResponse.ok) banks = (await banksResponse.json()) as BankOption[];
    else loadError = true;
    const investorLoads = await Promise.all(investors.map(async (investor) => {
      const [preferenceResponse, dematResponse] = await Promise.all([
        getData(`workspaces/${workspace.id}/investors/${investor.id}/funding-preferences/`, cookieHeader),
        getData(`workspaces/${workspace.id}/investors/${investor.id}/demats/`, cookieHeader),
      ]);
      return {
        id: investor.id,
        ok: preferenceResponse.ok && dematResponse.ok,
        preferences: preferenceResponse.ok ? (await preferenceResponse.json()) as FundingPreference[] : [],
        demats: dematResponse.ok ? (await dematResponse.json()) as Demat[] : [],
      };
    }));
    for (const result of investorLoads) {
      if (!result.ok) loadError = true;
      preferences[result.id] = result.preferences;
      linkedAccounts[result.id] = { demats: result.demats, upis: [] };
    }
    const upiLoads = await Promise.all(banks.map(async (bank) => {
      const response = await getData(`workspaces/${workspace.id}/banks/${bank.id}/upis/`, cookieHeader);
      return { bankId: bank.id, ok: response.ok, upis: response.ok ? (await response.json()) as Upi[] : [] };
    }));
    for (const result of upiLoads) {
      if (!result.ok) loadError = true;
      for (const upi of result.upis) {
        if (linkedAccounts[upi.holder]) {
          linkedAccounts[upi.holder].upis.push({ ...upi, bank_id: result.bankId });
        }
      }
    }
  }

  return <PrioritySettings workspace={workspace ?? null} investors={investors} banks={banks} preferences={preferences} linkedAccounts={linkedAccounts} loadError={loadError} />;
}
