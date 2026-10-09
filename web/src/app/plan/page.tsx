import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "@/lib/backend";
import { selectedWorkspace } from "@/lib/workspace";
import { splitPlanningSelections } from "@/lib/plan-presentation";
import PlanScreen, { type PlanLookups } from "./plan-screen";

type Workspace = { id: string; role: string };
type Investor = { id: string; name: string; planning_priority: number; active: boolean };
type Bank = { id: string; owner: string; bank_name: string; account_masked: string; current_balance: string; active: boolean; cross_funding_policy: string };
type IPO = { id: string; issuer_name: string; upper_price: string; lot_size: number; current_gmp_percent: string | null; close_date: string; status: string };
type Demat = { id: string; depository: string; dp_id_masked: string; client_id_masked: string; active: boolean };
type UPI = { id: string; handle_masked: string; holder: string; active: boolean; verified: boolean };
type Preference = { bank: string; priority: number; enabled: boolean };
type Decision = { ipo: string; selected: boolean; mode: string };
type Capital = { balance: string; blocked: string; planned: string; available: string };

async function getData(path: string, cookieHeader: string) {
  return fetch(backendUrl(path), { headers: { cookie: cookieHeader }, cache: "no-store" });
}

export default async function PlanPage() {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) redirect("/sign-in");
  const workspaceResponse = await getData("workspaces/", cookieHeader);
  if (!workspaceResponse.ok) redirect("/sign-in");
  const workspaces = (await workspaceResponse.json()) as Workspace[];
  const workspace = await selectedWorkspace(workspaces);
  if (!workspace) redirect("/settings/investors");
  const prefix = `workspaces/${workspace.id}`;
  const [investorResponse, bankResponse, ipoResponse, decisionResponse, capitalResponse] = await Promise.all([
    getData(`${prefix}/investors/`, cookieHeader),
    getData(`${prefix}/banks/`, cookieHeader),
    getData("ipos/", cookieHeader),
    getData(`${prefix}/ipo-decisions/`, cookieHeader),
    getData(`${prefix}/capital/`, cookieHeader),
  ]);
  const investors = investorResponse.ok ? ((await investorResponse.json()) as Investor[]) : [];
  const banks = bankResponse.ok ? ((await bankResponse.json()) as Bank[]) : [];
  const ipos = ipoResponse.ok ? ((await ipoResponse.json()) as IPO[]) : [];
  const decisions = decisionResponse.ok ? ((await decisionResponse.json()) as Decision[]) : [];
  const capital = capitalResponse.ok ? ((await capitalResponse.json()) as Capital) : null;
  const [dematLists, upiLists, preferenceLists] = await Promise.all([
    Promise.all(investors.map(async (investor) => {
      const response = await getData(`${prefix}/investors/${investor.id}/demats/`, cookieHeader);
      return { applicant: investor.id, items: response.ok ? ((await response.json()) as Demat[]) : [] };
    })),
    Promise.all(banks.map(async (bank) => {
      const response = await getData(`${prefix}/banks/${bank.id}/upis/`, cookieHeader);
      return { bank: bank.id, items: response.ok ? ((await response.json()) as UPI[]) : [] };
    })),
    Promise.all(investors.map(async (investor) => {
      const response = await getData(`${prefix}/investors/${investor.id}/funding-preferences/`, cookieHeader);
      return { applicant: investor.id, items: response.ok ? ((await response.json()) as Preference[]) : [] };
    })),
  ]);
  const selectionState = splitPlanningSelections(
    decisions.filter((decision) => decision.selected).map((decision) => ({ ipo: decision.ipo, mode: decision.mode })),
    Object.fromEntries(ipos.map((ipo) => [ipo.id, ipo.status])),
  );
  const lookups: PlanLookups = {
    ipos: Object.fromEntries(ipos.map((ipo) => [ipo.id, { name: ipo.issuer_name, upperPrice: ipo.upper_price, lotSize: ipo.lot_size, gmpPercent: ipo.current_gmp_percent, closeDate: ipo.close_date }])),
    applicants: Object.fromEntries(investors.map((investor) => [investor.id, { name: investor.name, priority: investor.planning_priority, active: investor.active }])),
    demats: Object.fromEntries(dematLists.flatMap((group) => group.items.map((demat) => [demat.id, { label: `${demat.depository} ${demat.dp_id_masked} / ${demat.client_id_masked}`, applicant: group.applicant, active: demat.active }]))),
    banks: Object.fromEntries(banks.map((bank) => [bank.id, { label: `${bank.bank_name} ${bank.account_masked}`, owner: bank.owner, balance: bank.current_balance, active: bank.active, policy: bank.cross_funding_policy }])),
    upis: Object.fromEntries(upiLists.flatMap((group) => group.items.map((upi) => [upi.id, { label: upi.handle_masked, bank: group.bank, holder: upi.holder, active: upi.active, verified: upi.verified }]))),
    preferences: Object.fromEntries(preferenceLists.map((group) => [group.applicant, group.items])),
    selectedIpos: selectionState.available,
    unavailableSelectedIpoCount: selectionState.unavailableCount,
    capital,
  };
  return <PlanScreen workspaceId={workspace.id} canEdit={workspace.role !== "VIEWER"} lookups={lookups} />;
}
