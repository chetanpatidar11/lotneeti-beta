"use client";

import { FormEvent, useState } from "react";
import { ConfirmationDialog } from "@/components/confirmation-dialog";
import { Drawer } from "@/components/drawer";
import { EmptyState, PageHeader, SectionHeading, StatusBadge } from "@/components/ui";
import { formatInr } from "@/lib/money";
import { movePriority, sortByPriority } from "@/lib/priorities";
import { applySettingsAction, toggleSelected, type SettingsKind } from "@/lib/settings-removal";
import PreferredFunding, { type BankOption, type FundingPreference } from "./preferred-funding";
import AccountImport from "./account-import";

type Workspace = { id: string; name: string; role: string };
type Investor = { id: string; name: string; pan_masked: string; planning_priority: number; active: boolean; payment_ready: boolean; payment_hint_masked: string };
type Demat = { id: string; depository: string; dp_id_masked: string; client_id_masked: string; broker: string; active: boolean };
type Upi = { id: string; holder: string; bank_id: string; handle_masked: string; active: boolean; verified: boolean };
type LinkedAccounts = Record<string, { demats: Demat[]; upis: Upi[] }>;
type Tab = "investors" | "funding" | "accounts" | "import";
type AddAccountKind = "demat" | "bank" | "upi";
type Selection = Record<SettingsKind, string[]>;
type AccountRow = { id: string; name: string; owner: string; detail: string; active: boolean; verified?: boolean; isPlaceholder?: boolean };
const emptySelection = (): Selection => ({ investor: [], demat: [], bank: [], upi: [] });

async function accountError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null) as Record<string, unknown> | null;
  if (typeof body?.detail === "string") return body.detail;
  const messages = Object.values(body ?? {}).flatMap((value) =>
    typeof value === "string" ? [value] : Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [],
  );
  return messages[0] ?? fallback;
}

const labelForKind: Record<SettingsKind, string> = {
  investor: "investor",
  demat: "demat account",
  bank: "bank account",
  upi: "UPI",
};

function AccountTable({
  title, kind, rows, selected, canEdit, busy, onToggle, onSelectAll, onAction, onAdd, onEdit, addLabel, addDisabled,
}: {
  title: string;
  kind: SettingsKind;
  rows: AccountRow[];
  selected: string[];
  canEdit: boolean;
  busy: boolean;
  onToggle: (kind: SettingsKind, id: string, checked: boolean) => void;
  onSelectAll: (kind: SettingsKind, ids: string[], checked: boolean) => void;
  onAction: (kind: SettingsKind, ids: string[], action: "deactivate" | "activate" | "delete") => void;
  onAdd: () => void;
  onEdit?: (id: string) => void;
  addLabel: string;
  addDisabled: boolean;
}) {
  const visible = [...new Map(rows.map((row) => [row.id, row])).values()].sort((a, b) => Number(b.active) - Number(a.active));
  const selectedActive = visible.filter((row) => row.active && selected.includes(row.id)).map((row) => row.id);
  const selectedInactive = visible.filter((row) => !row.active && !row.isPlaceholder && selected.includes(row.id)).map((row) => row.id);
  return <section className="settings-account-group" aria-label={title}>
    <SectionHeading title={title} action={canEdit && <div className="settings-section-actions"><button type="button" className="button-secondary" disabled={busy || addDisabled} onClick={onAdd}>+ {addLabel}</button>{visible.length > 0 && <><button type="button" className="button-secondary" disabled={busy} onClick={() => onSelectAll(kind, visible.map((row) => row.id), !visible.every((row) => selected.includes(row.id)))}>{visible.every((row) => selected.includes(row.id)) ? "Clear selection" : "Select all"}</button>{selectedActive.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAction(kind, selectedActive, "deactivate")}>Deactivate selected ({selectedActive.length})</button>}{selectedInactive.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAction(kind, selectedInactive, "activate")}>Activate selected ({selectedInactive.length})</button>}{selected.length > 0 && <button type="button" className="button-danger" disabled={busy} onClick={() => onAction(kind, selected, "delete")}>Delete selected ({selected.length})</button>}</>}</div>} />
    {visible.length === 0 ? <div className="settings-account-empty">No {kind === "upi" ? "UPI IDs" : title.toLowerCase()} added yet.</div> : <div className="settings-table-wrap"><table className="settings-table"><thead><tr>
      {canEdit && <th scope="col" className="settings-select-cell"><label><input type="checkbox" aria-label={`Select all ${title.toLowerCase()}`} checked={visible.every((row) => selected.includes(row.id))} disabled={busy} onChange={(event) => onSelectAll(kind, visible.map((row) => row.id), event.target.checked)} /></label></th>}
      <th scope="col">Account</th><th scope="col">Investor</th><th scope="col">Details</th><th scope="col">Status</th><th scope="col">Action</th>
    </tr></thead><tbody>{visible.map((row) => <tr key={row.id} className={row.active ? "" : "settings-inactive-row"}>
      {canEdit && <td data-label="Select" className="settings-select-cell"><label><input type="checkbox" aria-label={`Select ${row.name}`} checked={selected.includes(row.id)} disabled={busy} onChange={(event) => onToggle(kind, row.id, event.target.checked)} /></label></td>}
      <th scope="row" data-label="Account">{row.name}</th><td data-label="Investor">{row.owner}</td><td data-label="Details">{row.detail}</td><td data-label="Status"><StatusBadge tone={row.active ? "positive" : row.isPlaceholder ? "warning" : "neutral"}>{row.isPlaceholder ? "Needs details" : row.active ? "Active" : "Inactive"}</StatusBadge></td>
      <td data-label="Action">{canEdit ? <div className="settings-row-actions">{onEdit && !(kind === "upi" && row.verified) && <button type="button" className="button-secondary" disabled={busy} onClick={() => onEdit(row.id)}>{kind === "upi" ? "Verify" : row.isPlaceholder ? "Complete details" : "Edit"}</button>}{!row.isPlaceholder && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAction(kind, [row.id], row.active ? "deactivate" : "activate")}>{row.active ? "Deactivate" : "Activate"}</button>}<button type="button" className="button-ghost-danger" disabled={busy} onClick={() => onAction(kind, [row.id], "delete")}>Delete</button></div> : "—"}</td>
    </tr>)}</tbody></table></div>}
  </section>;
}

export default function PrioritySettings({
  workspace: initialWorkspace,
  investors: initialInvestors,
  banks: initialBanks,
  preferences: initialPreferences,
  linkedAccounts: initialLinkedAccounts,
  loadError,
}: {
  workspace: Workspace | null;
  investors: Investor[];
  banks: BankOption[];
  preferences: Record<string, FundingPreference[]>;
  linkedAccounts: LinkedAccounts;
  loadError: boolean;
}) {
  const [workspace, setWorkspace] = useState(initialWorkspace);
  const [investors, setInvestors] = useState(sortByPriority(initialInvestors));
  const [banks, setBanks] = useState(initialBanks);
  const [linkedAccounts, setLinkedAccounts] = useState(initialLinkedAccounts);
  const [preferences, setPreferences] = useState(initialPreferences);
  const [tab, setTab] = useState<Tab>("investors");
  const [selected, setSelected] = useState<Selection>(emptySelection);
  const [pendingRemoval, setPendingRemoval] = useState<{ kind: SettingsKind; ids: string[] } | null>(null);
  const [selectedInvestor, setSelectedInvestor] = useState<string | null>(null);
  const [showAddInvestor, setShowAddInvestor] = useState(false);
  const [addAccountKind, setAddAccountKind] = useState<AddAccountKind | null>(null);
  const [editDematId, setEditDematId] = useState<string | null>(null);
  const [editDpId, setEditDpId] = useState("");
  const [editClientId, setEditClientId] = useState("");
  const [editBroker, setEditBroker] = useState("");
  const [editBankId, setEditBankId] = useState<string | null>(null);
  const [editBankOwner, setEditBankOwner] = useState("");
  const [editBankName, setEditBankName] = useState("");
  const [editAccountNumber, setEditAccountNumber] = useState("");
  const [verifyUpiId, setVerifyUpiId] = useState<string | null>(null);
  const [accountInvestorId, setAccountInvestorId] = useState(initialInvestors.find((investor) => investor.active)?.id ?? "");
  const [depository, setDepository] = useState<"CDSL" | "NSDL">("CDSL");
  const [dpId, setDpId] = useState("");
  const [clientId, setClientId] = useState("");
  const [broker, setBroker] = useState("");
  const [bankName, setBankName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [openingBalance, setOpeningBalance] = useState("0");
  const [upiBankId, setUpiBankId] = useState(initialBanks.find((bank) => bank.active)?.id ?? "");
  const [upiHandle, setUpiHandle] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [name, setName] = useState("");
  const [pan, setPan] = useState("");
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState(false);
  const [busy, setBusy] = useState(false);
  const canEdit = workspace?.role !== "VIEWER";
  const activeInvestors = sortByPriority(investors.filter((investor) => investor.active));
  const investorsWithoutDemat = activeInvestors.filter((investor) => !linkedAccounts[investor.id]?.demats.length);
  const visibleInvestors = [...activeInvestors, ...sortByPriority(investors.filter((investor) => !investor.active))];
  const selectedActiveInvestors = visibleInvestors.filter((investor) => investor.active && selected.investor.includes(investor.id)).map((investor) => investor.id);
  const selectedInactiveInvestors = visibleInvestors.filter((investor) => !investor.active && selected.investor.includes(investor.id)).map((investor) => investor.id);
  const focusedInvestor = investors.find((investor) => investor.id === selectedInvestor);
  const investorName = (id: string) => investors.find((item) => item.id === id)?.name ?? "Investor";
  const dematRows = Object.entries(linkedAccounts).flatMap(([owner, accounts]) => accounts.demats.map((demat) => ({
    id: demat.id, name: `${demat.depository} · ${demat.client_id_masked}`, owner: investorName(owner),
    detail: [demat.dp_id_masked, demat.broker].filter(Boolean).join(" · "), active: demat.active,
  })));
  const bankRows = banks.map((bank) => ({
    id: bank.id, name: `${bank.is_placeholder ? "Bank details needed" : bank.bank_name} · ${bank.account_masked}`, owner: bank.is_placeholder ? "Choose holder" : investorName(bank.owner),
    detail: bank.is_placeholder ? "UPI reference · add real bank details" : `Balance ${formatInr(bank.current_balance)}`, active: bank.active, isPlaceholder: bank.is_placeholder,
  }));
  const upiRows = Object.values(linkedAccounts).flatMap((accounts) => accounts.upis.map((upi) => ({
    id: upi.id, name: upi.handle_masked, owner: banks.find((bank) => bank.id === upi.bank_id)?.is_placeholder ? "Choose holder" : investorName(upi.holder),
    detail: `${banks.find((bank) => bank.id === upi.bank_id)?.bank_name ?? "Bank"} · ${upi.verified ? "Verified" : "Not verified"}`,
    active: upi.active, verified: upi.verified,
  })));
  const accountCount = new Set(dematRows.map((row) => row.id)).size + new Set(bankRows.map((row) => row.id)).size + new Set(upiRows.map((row) => row.id)).size;

  function note(text: string, error = false) {
    setMessage(text);
    setMessageError(error);
  }

  function changeTab(next: Tab) {
    setTab(next);
    setSelectedInvestor(null);
    setSelected(emptySelection());
  }

  function toggle(kind: SettingsKind, id: string, checked: boolean) {
    setSelected((current) => ({ ...current, [kind]: toggleSelected(current[kind], id, checked) }));
  }

  function selectAll(kind: SettingsKind, ids: string[], checked: boolean) {
    setSelected((current) => ({ ...current, [kind]: checked ? ids : [] }));
  }

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const response = await fetch("/api/workspaces", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: workspaceName }),
      });
      if (!response.ok) throw new Error("Create failed");
      setWorkspace((await response.json()) as Workspace);
      note("");
    } catch {
      note("We could not create the workspace. Please try again.", true);
    } finally { setBusy(false); }
  }

  async function addInvestor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/investors`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, pan, planning_priority: Math.max(0, ...investors.map((item) => item.planning_priority)) + 1 }),
      });
      if (!response.ok) throw new Error("Create failed");
      const investor = (await response.json()) as Investor;
      setInvestors(sortByPriority([...investors, investor]));
      setName(""); setPan(""); setShowAddInvestor(false);
      note("Investor added.");
    } catch {
      note("Check the investor details and try again.", true);
    } finally { setBusy(false); }
  }

  function openAddAccount(kind: AddAccountKind) {
    setAccountInvestorId((kind === "demat" ? investorsWithoutDemat : activeInvestors)[0]?.id ?? "");
    setUpiBankId(banks.find((bank) => bank.active)?.id ?? "");
    setAddAccountKind(kind);
  }

  async function addDemat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !accountInvestorId) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/investors/${accountInvestorId}/demats`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ depository, dp_id: dpId, client_id: clientId, broker }),
      });
      if (!response.ok) throw new Error(await accountError(response, "Check the demat details and try again."));
      const demat = await response.json() as Demat;
      setLinkedAccounts((current) => {
        const accounts = current[accountInvestorId] ?? { demats: [], upis: [] };
        return { ...current, [accountInvestorId]: { ...accounts, demats: [...accounts.demats, demat] } };
      });
      setAddAccountKind(null);
      setDpId(""); setClientId(""); setBroker("");
      note("Demat account added.");
    } catch (error) {
      note(error instanceof Error ? error.message : "Check the demat details and try again.", true);
    } finally { setBusy(false); }
  }

  function openEditBank(id: string) {
    const bank = banks.find((item) => item.id === id);
    if (!bank) return;
    setEditBankId(id);
    setEditBankOwner(bank.is_placeholder ? "" : bank.owner);
    setEditBankName(bank.is_placeholder ? "" : bank.bank_name);
    setEditAccountNumber("");
  }

  function openEditDemat(id: string) {
    const demat = Object.values(linkedAccounts).flatMap((accounts) => accounts.demats).find((item) => item.id === id);
    if (!demat) return;
    setEditDematId(id);
    setEditDpId("");
    setEditClientId("");
    setEditBroker(demat.broker);
  }

  async function saveDemat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !editDematId) return;
    const ownerId = Object.entries(linkedAccounts).find(([, accounts]) => accounts.demats.some((item) => item.id === editDematId))?.[0];
    if (!ownerId) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/investors/${ownerId}/demats/${editDematId}`, {
        method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...(editDpId ? { dp_id: editDpId } : {}), ...(editClientId ? { client_id: editClientId } : {}), broker: editBroker }),
      });
      if (!response.ok) throw new Error(await accountError(response, "Check the demat details and try again."));
      const saved = await response.json() as Demat;
      setLinkedAccounts((current) => ({ ...current, [ownerId]: {
        ...current[ownerId], demats: current[ownerId].demats.map((item) => item.id === saved.id ? saved : item),
      } }));
      setEditDematId(null);
      note("Demat details saved.");
    } catch (error) {
      note(error instanceof Error ? error.message : "Check the demat details and try again.", true);
    } finally { setBusy(false); }
  }

  async function saveBank(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !editBankId) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks/${editBankId}`, {
        method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify({ owner: editBankOwner, bank_name: editBankName, account_number: editAccountNumber }),
      });
      if (!response.ok) throw new Error(await accountError(response, "Check the bank details and try again."));
      const updated = await response.json() as BankOption;
      setBanks((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (banks.find((item) => item.id === updated.id)?.is_placeholder) {
        setLinkedAccounts((current) => {
          const moved = Object.values(current).flatMap((accounts) => accounts.upis).filter((item) => item.bank_id === updated.id && !item.verified).map((item) => ({ ...item, holder: updated.owner }));
          const next = Object.fromEntries(Object.entries(current).map(([id, accounts]) => [id, {
            ...accounts, upis: accounts.upis.filter((item) => !moved.some((upi) => upi.id === item.id)),
          }]));
          next[updated.owner] = { ...(next[updated.owner] ?? { demats: [], upis: [] }), upis: [...(next[updated.owner]?.upis ?? []), ...moved] };
          return next;
        });
      }
      setEditBankId(null);
      note("Bank details saved. Activate this bank when you are ready to use it.");
    } catch (error) {
      note(error instanceof Error ? error.message : "Check the bank details and try again.", true);
    } finally { setBusy(false); }
  }

  async function verifyUpi() {
    if (!workspace || !verifyUpiId) return;
    const upi = Object.values(linkedAccounts).flatMap((accounts) => accounts.upis).find((item) => item.id === verifyUpiId);
    if (!upi) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks/${upi.bank_id}/upis/${upi.id}`, {
        method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ verified: true }),
      });
      if (!response.ok) throw new Error(await accountError(response, "Complete and activate the bank first."));
      setLinkedAccounts((current) => Object.fromEntries(Object.entries(current).map(([id, accounts]) => [id, {
        ...accounts, upis: accounts.upis.map((item) => item.id === upi.id ? { ...item, verified: true } : item),
      }])));
      const investorsResponse = await fetch(`/api/workspaces/${workspace.id}/investors`);
      if (investorsResponse.ok) setInvestors(sortByPriority(await investorsResponse.json() as Investor[]));
      setVerifyUpiId(null);
      note("UPI verified.");
    } catch (error) {
      note(error instanceof Error ? error.message : "We could not verify this UPI.", true);
    } finally { setBusy(false); }
  }

  async function addBank(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !accountInvestorId) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ owner: accountInvestorId, bank_name: bankName, account_number: accountNumber, initial_balance: openingBalance }),
      });
      if (!response.ok) throw new Error(await accountError(response, "Check the bank details and try again."));
      const bank = await response.json() as BankOption;
      setBanks((current) => [...current, bank]);
      setAddAccountKind(null);
      setBankName(""); setAccountNumber(""); setOpeningBalance("0");
      note("Bank account added.");
    } catch (error) {
      note(error instanceof Error ? error.message : "Check the bank details and try again.", true);
    } finally { setBusy(false); }
  }

  async function addUpi(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !accountInvestorId || !upiBankId) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks/${upiBankId}/upis`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ holder: accountInvestorId, handle: upiHandle }),
      });
      if (!response.ok) throw new Error(await accountError(response, "Check the UPI details and try again."));
      const upi = await response.json() as Omit<Upi, "bank_id">;
      setLinkedAccounts((current) => {
        const accounts = current[accountInvestorId] ?? { demats: [], upis: [] };
        return { ...current, [accountInvestorId]: { ...accounts, upis: [...accounts.upis, { ...upi, bank_id: upiBankId }] } };
      });
      setAddAccountKind(null);
      setUpiHandle("");
      note("UPI added. It remains unverified until you verify it.");
    } catch (error) {
      note(error instanceof Error ? error.message : "Check the UPI details and try again.", true);
    } finally { setBusy(false); }
  }

  async function savePriority() {
    if (!workspace) return;
    setBusy(true);
    try {
      for (const investor of activeInvestors) {
        const response = await fetch(`/api/workspaces/${workspace.id}/investors/${investor.id}`, {
          method: "PATCH", headers: { "content-type": "application/json" },
          body: JSON.stringify({ planning_priority: investor.planning_priority }),
        });
        if (!response.ok) throw new Error("Save failed");
      }
      setInvestors(sortByPriority(investors));
      note("Planning priority saved.");
    } catch {
      note("We could not save the order. Please try again.", true);
    } finally { setBusy(false); }
  }

  async function updateItems(kind: SettingsKind, ids: string[], action: "deactivate" | "activate" | "delete") {
    if (!workspace || ids.length === 0) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/settings/items`, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind, ids, action }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { message?: string };
        throw new Error(body.message ?? "We could not change these items. Please try again.");
      }
      const next = applySettingsAction({ investors, banks, linkedAccounts }, kind, ids, action);
      setInvestors(next.investors);
      setBanks(next.banks);
      setLinkedAccounts(next.linkedAccounts);
      setSelected(emptySelection());
      if (action === "delete") {
        const deleted = new Set(ids);
        setPreferences((current) => Object.fromEntries(Object.entries(current)
          .filter(([investorId]) => kind !== "investor" || !deleted.has(investorId))
          .map(([investorId, rows]) => [investorId, kind === "bank" ? rows.filter((row) => !deleted.has(row.bank)) : rows])));
      }
      if (kind === "investor" && selectedInvestor && ids.includes(selectedInvestor)) setSelectedInvestor(null);
      note(`${ids.length} ${labelForKind[kind]}${ids.length === 1 ? "" : "s"} ${action === "delete" ? "permanently deleted" : action === "activate" ? "activated" : "deactivated"}.`);
    } catch (error) {
      note(error instanceof Error ? error.message : "We could not change these items. Please try again.", true);
    } finally {
      setBusy(false);
      setPendingRemoval(null);
    }
  }

  function itemAction(kind: SettingsKind, ids: string[], action: "deactivate" | "activate" | "delete") {
    if (action === "delete") setPendingRemoval({ kind, ids });
    else void updateItems(kind, ids, action);
  }

  const pendingCount = pendingRemoval?.ids.length ?? 0;
  const pendingName = pendingRemoval ? labelForKind[pendingRemoval.kind] : "item";
  const confirmationDetail = pendingRemoval?.kind === "investor" || pendingRemoval?.kind === "bank"
    ? "Linked accounts without applications will also be deleted. Bank balance history stays in Funds."
    : "";

  return <main className="page settings-page"><div className="shell settings-shell">
    <PageHeader eyebrow="Workspace" title="Settings" description={workspace ? workspace.name : "Set up a workspace to start planning."} />
    {message && <p role={messageError ? "alert" : "status"} className={messageError ? "settings-message error" : "settings-message"}>{message}</p>}
    {loadError ? <div className="plan-error" role="alert">Settings could not be loaded. <button type="button" className="button-secondary" onClick={() => window.location.reload()}>Retry</button></div> : !workspace ? <form onSubmit={createWorkspace} className="sign-in-form settings-create-workspace">
      <label htmlFor="workspace-name">Workspace name</label><input id="workspace-name" required value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} />
      <button type="submit" disabled={busy}>Create workspace</button>
    </form> : <>
      <nav className="settings-tabs" aria-label="Settings sections">
        {([["investors", "Investors"], ["funding", "Funding Preferences"], ["accounts", "Accounts"], ["import", "Import"]] as const).map(([key, label]) => <button key={key} type="button" className={tab === key ? "settings-tab active" : "settings-tab"} aria-current={tab === key ? "page" : undefined} onClick={() => changeTab(key)}>{label}</button>)}
      </nav>
      {tab === "investors" && <section aria-label="Investors">
        <SectionHeading title="Investors" detail="Active investors are planned first. Inactive investors stay visible here." action={canEdit && <div className="settings-section-actions">
          {visibleInvestors.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => selectAll("investor", visibleInvestors.map((investor) => investor.id), !visibleInvestors.every((investor) => selected.investor.includes(investor.id)))}>{visibleInvestors.every((investor) => selected.investor.includes(investor.id)) ? "Clear selection" : "Select all"}</button>}
          {selectedActiveInvestors.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => itemAction("investor", selectedActiveInvestors, "deactivate")}>Deactivate selected ({selectedActiveInvestors.length})</button>}
          {selectedInactiveInvestors.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => itemAction("investor", selectedInactiveInvestors, "activate")}>Activate selected ({selectedInactiveInvestors.length})</button>}
          {selected.investor.length > 0 && <button type="button" className="button-danger" disabled={busy} onClick={() => itemAction("investor", selected.investor, "delete")}>Delete selected ({selected.investor.length})</button>}
          <button type="button" className="button-secondary" disabled={busy || activeInvestors.length === 0} onClick={() => void savePriority()}>Save priority</button><button type="button" onClick={() => setShowAddInvestor(true)}>+ Add investor</button>
        </div>} />
        {visibleInvestors.length === 0 ? <EmptyState title="No investors yet" detail="Add an investor to begin planning IPO applications." /> : <div className="settings-table-wrap"><table className="settings-table"><thead><tr>
          {canEdit && <th scope="col" className="settings-select-cell"><label><input type="checkbox" aria-label="Select all investors" checked={visibleInvestors.every((investor) => selected.investor.includes(investor.id))} disabled={busy} onChange={(event) => selectAll("investor", visibleInvestors.map((investor) => investor.id), event.target.checked)} /></label></th>}
          <th scope="col">Investor</th><th scope="col">PAN</th><th scope="col">Priority</th><th scope="col">Demat</th><th scope="col">Banks</th><th scope="col">UPIs</th><th scope="col">Status</th><th scope="col">Actions</th>
        </tr></thead><tbody>{visibleInvestors.map((investor, index) => <tr key={investor.id} className={investor.active ? "" : "settings-inactive-row"}>
          {canEdit && <td data-label="Select" className="settings-select-cell"><label><input type="checkbox" aria-label={`Select ${investor.name}`} checked={selected.investor.includes(investor.id)} disabled={busy} onChange={(event) => toggle("investor", investor.id, event.target.checked)} /></label></td>}
          <th scope="row" data-label="Investor">{investor.name}</th><td data-label="PAN">{investor.pan_masked}</td>
          <td data-label="Priority">{!investor.active ? "—" : <div className="settings-priority"><input aria-label={`Priority for ${investor.name}`} type="number" min="1" value={investor.planning_priority} disabled={!canEdit || busy} onChange={(event) => setInvestors(investors.map((item) => item.id === investor.id ? { ...item, planning_priority: Math.max(1, Number(event.target.value)) } : item))} />{canEdit && <span className="settings-order"><button type="button" className="button-ghost" aria-label={`Move ${investor.name} up`} disabled={index === 0 || busy} onClick={() => setInvestors([...movePriority(activeInvestors, index, -1), ...investors.filter((item) => !item.active)])}>↑</button><button type="button" className="button-ghost" aria-label={`Move ${investor.name} down`} disabled={index === activeInvestors.length - 1 || busy} onClick={() => setInvestors([...movePriority(activeInvestors, index, 1), ...investors.filter((item) => !item.active)])}>↓</button></span>}</div>}</td>
          <td data-label="Demat">{linkedAccounts[investor.id]?.demats.filter((item) => item.active).length ?? 0}</td>
          <td data-label="Banks">{banks.filter((bank) => bank.owner === investor.id && bank.active).length}</td>
          <td data-label="UPIs">{linkedAccounts[investor.id]?.upis.filter((item) => item.active).length ?? 0}</td>
          <td data-label="Status"><StatusBadge tone={!investor.active ? "neutral" : investor.payment_ready ? "positive" : "warning"}>{!investor.active ? "Inactive" : investor.payment_ready ? "Active" : "Payment needed"}</StatusBadge></td>
          <td data-label="Actions" className="settings-row-actions"><button type="button" className="button-secondary" onClick={() => setSelectedInvestor(investor.id)}>View</button>{canEdit && <><button type="button" className="button-secondary" disabled={busy} onClick={() => itemAction("investor", [investor.id], investor.active ? "deactivate" : "activate")}>{investor.active ? "Deactivate" : "Activate"}</button><button type="button" className="button-ghost-danger" disabled={busy} onClick={() => itemAction("investor", [investor.id], "delete")}>Delete</button></>}</td>
        </tr>)}</tbody></table></div>}
      </section>}

      {tab === "funding" && <section aria-label="Funding preferences"><SectionHeading title="Funding Preferences" detail="Choose an investor to review and order their preferred accounts." />
        {activeInvestors.length === 0 ? <EmptyState title="No active investors" detail="Add or activate an investor before setting funding preferences." /> : <div className="settings-funding-list">{activeInvestors.map((investor) => <button type="button" key={investor.id} className="settings-funding-row" onClick={() => setSelectedInvestor(investor.id)}><span><strong>{investor.name}</strong><small>{investor.pan_masked}</small></span><span>{preferences[investor.id]?.filter((item) => item.enabled).length ?? 0} preferred · {banks.filter((bank) => bank.owner === investor.id && bank.active).length} own bank(s)</span><span aria-hidden="true">›</span></button>)}</div>}
      </section>}

      {tab === "accounts" && <section aria-label="Accounts"><SectionHeading title="Linked accounts" detail={accountCount > 0 ? "Demat, bank and UPI accounts for this workspace." : undefined} action={accountCount > 0 ? <span className="settings-account-count">{accountCount} total</span> : undefined} />
        {accountCount === 0 ? <div className="settings-accounts-empty"><span className="settings-accounts-empty-mark" aria-hidden="true">+</span><div><p className="settings-accounts-empty-kicker">GET STARTED</p><h3>{activeInvestors.length > 0 ? "Connect your first account" : investors.length > 0 ? "Activate an investor to add accounts" : "Set up your investor accounts"}</h3><p>{activeInvestors.length > 0 ? "Add a demat and bank account for an investor. You can link a UPI ID after adding a bank." : investors.length > 0 ? "Your investors are inactive. Activate one before linking a demat, bank or UPI account." : "Add an investor, then link their demat, bank and UPI details for IPO planning."}</p><div className="settings-accounts-empty-actions">{canEdit && (activeInvestors.length > 0 ? <><button type="button" onClick={() => openAddAccount("demat")}>+ Add demat</button><button type="button" className="button-secondary" onClick={() => openAddAccount("bank")}>+ Add bank</button></> : investors.length > 0 ? <button type="button" onClick={() => changeTab("investors")}>View investors</button> : <button type="button" onClick={() => setShowAddInvestor(true)}>+ Add investor</button>)}{canEdit && <button type="button" className="text-button" onClick={() => changeTab("import")}>Import accounts →</button>}</div></div></div> : <>
          <AccountTable title="Demat Accounts" kind="demat" rows={dematRows} selected={selected.demat} canEdit={canEdit} busy={busy} onToggle={toggle} onSelectAll={selectAll} onAction={itemAction} onAdd={() => openAddAccount("demat")} onEdit={openEditDemat} addLabel="Add demat" addDisabled={investorsWithoutDemat.length === 0} />
          <AccountTable title="Bank Accounts" kind="bank" rows={bankRows} selected={selected.bank} canEdit={canEdit} busy={busy} onToggle={toggle} onSelectAll={selectAll} onAction={itemAction} onAdd={() => openAddAccount("bank")} onEdit={openEditBank} addLabel="Add bank" addDisabled={activeInvestors.length === 0} />
          <AccountTable title="UPIs" kind="upi" rows={upiRows} selected={selected.upi} canEdit={canEdit} busy={busy} onToggle={toggle} onSelectAll={selectAll} onAction={itemAction} onAdd={() => openAddAccount("upi")} onEdit={setVerifyUpiId} addLabel="Add UPI" addDisabled={activeInvestors.length === 0 || banks.every((bank) => !bank.active)} />
        </>}
      </section>}

      {tab === "import" && <AccountImport workspaceId={workspace.id} canEdit={canEdit} />}
      {addAccountKind === "demat" && <Drawer title="Add demat account" onClose={() => setAddAccountKind(null)}><form className="sign-in-form" onSubmit={addDemat}>
        <label htmlFor="demat-owner">Investor</label><select id="demat-owner" value={accountInvestorId} onChange={(event) => setAccountInvestorId(event.target.value)} required>{investorsWithoutDemat.map((investor) => <option key={investor.id} value={investor.id}>{investor.name}</option>)}</select>
        <label htmlFor="demat-depository">Depository</label><select id="demat-depository" value={depository} onChange={(event) => setDepository(event.target.value as "CDSL" | "NSDL")}><option value="CDSL">CDSL</option><option value="NSDL">NSDL</option></select>
        <label htmlFor="demat-dp-id">DP ID {depository === "NSDL" ? "" : "(optional for CDSL)"}</label><input id="demat-dp-id" required={depository === "NSDL"} value={dpId} onChange={(event) => setDpId(event.target.value)} />
        {depository === "CDSL" && <small>Leave blank when Client ID contains the complete BO ID.</small>}
        <label htmlFor="demat-client-id">Client ID</label><input id="demat-client-id" required value={clientId} onChange={(event) => setClientId(event.target.value)} />
        <label htmlFor="demat-broker">Broker (optional)</label><input id="demat-broker" value={broker} onChange={(event) => setBroker(event.target.value)} />
        <button type="submit" disabled={busy}>Add demat account</button>
      </form></Drawer>}
      {editDematId && <Drawer title="Edit demat account" onClose={() => setEditDematId(null)}><form className="sign-in-form" onSubmit={saveDemat}>
        <p className="form-note">Leave an ID field blank to keep its current value.</p>
        <label htmlFor="edit-dp-id">New DP ID</label><input id="edit-dp-id" value={editDpId} onChange={(event) => setEditDpId(event.target.value)} />
        <label htmlFor="edit-client-id">New Client ID</label><input id="edit-client-id" value={editClientId} onChange={(event) => setEditClientId(event.target.value)} />
        <label htmlFor="edit-broker">Broker</label><input id="edit-broker" value={editBroker} onChange={(event) => setEditBroker(event.target.value)} />
        <button type="submit" disabled={busy}>Save demat</button>
      </form></Drawer>}
      {editBankId && <Drawer title="Complete bank details" onClose={() => setEditBankId(null)}><form className="sign-in-form" onSubmit={saveBank}>
        <p className="form-note">The imported UPI ID was saved as an inactive reference. Enter the real bank details before using this account for planning.</p>
        <label htmlFor="edit-bank-owner">Bank and UPI holder</label><select id="edit-bank-owner" value={editBankOwner} onChange={(event) => setEditBankOwner(event.target.value)} required><option value="">Choose holder</option>{activeInvestors.map((investor) => <option key={investor.id} value={investor.id}>{investor.name}</option>)}</select>
        <label htmlFor="edit-bank-name">Bank name</label><input id="edit-bank-name" required value={editBankName} onChange={(event) => setEditBankName(event.target.value)} />
        <label htmlFor="edit-bank-number">Real account number</label><input id="edit-bank-number" required autoComplete="off" value={editAccountNumber} onChange={(event) => setEditAccountNumber(event.target.value)} />
        <button type="submit" disabled={busy}>Save bank details</button>
      </form></Drawer>}
      {addAccountKind === "bank" && <Drawer title="Add bank account" onClose={() => setAddAccountKind(null)}><form className="sign-in-form" onSubmit={addBank}>
        <label htmlFor="account-bank-owner">Owner</label><select id="account-bank-owner" value={accountInvestorId} onChange={(event) => setAccountInvestorId(event.target.value)} required>{activeInvestors.map((investor) => <option key={investor.id} value={investor.id}>{investor.name}</option>)}</select>
        <label htmlFor="account-bank-name">Bank name</label><input id="account-bank-name" required value={bankName} onChange={(event) => setBankName(event.target.value)} />
        <label htmlFor="account-bank-number">Account number</label><input id="account-bank-number" required autoComplete="off" value={accountNumber} onChange={(event) => setAccountNumber(event.target.value)} />
        <label htmlFor="account-opening-balance">Opening Balance (₹)</label><input id="account-opening-balance" type="number" min="0" step="0.01" required value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} />
        <button type="submit" disabled={busy}>Add bank</button>
      </form></Drawer>}
      {addAccountKind === "upi" && <Drawer title="Add UPI" onClose={() => setAddAccountKind(null)}><form className="sign-in-form" onSubmit={addUpi}>
        <label htmlFor="upi-holder">Investor</label><select id="upi-holder" value={accountInvestorId} onChange={(event) => setAccountInvestorId(event.target.value)} required>{activeInvestors.map((investor) => <option key={investor.id} value={investor.id}>{investor.name}</option>)}</select>
        <label htmlFor="upi-bank">Bank account</label><select id="upi-bank" value={upiBankId} onChange={(event) => setUpiBankId(event.target.value)} required>{banks.filter((bank) => bank.active).map((bank) => <option key={bank.id} value={bank.id}>{bank.bank_name} · {bank.account_masked}</option>)}</select>
        <label htmlFor="upi-handle">UPI ID</label><input id="upi-handle" required autoComplete="off" placeholder="name@provider" value={upiHandle} onChange={(event) => setUpiHandle(event.target.value)} />
        <p className="form-note">New UPI IDs are unverified until verified separately.</p>
        <button type="submit" disabled={busy}>Add UPI</button>
      </form></Drawer>}
      {focusedInvestor && <Drawer title={focusedInvestor.name} onClose={() => setSelectedInvestor(null)}><div className="settings-investor-detail"><p><strong>PAN</strong><span>{focusedInvestor.pan_masked}</span></p><p><strong>Status</strong><StatusBadge tone={!focusedInvestor.active ? "neutral" : focusedInvestor.payment_ready ? "positive" : "warning"}>{!focusedInvestor.active ? "Inactive" : focusedInvestor.payment_ready ? "Active" : "Payment needed"}</StatusBadge></p>{!focusedInvestor.payment_ready && <p><strong>UPI reference</strong><span>{focusedInvestor.payment_hint_masked} · Complete the shared bank details and verify its UPI before planning.</span></p>}</div><div className="settings-linked"><h3>Demat Account</h3>{linkedAccounts[focusedInvestor.id]?.demats.length ? linkedAccounts[focusedInvestor.id].demats.map((demat) => <p key={demat.id}>{demat.depository} · {demat.dp_id_masked} / {demat.client_id_masked} <small>{demat.broker} · {demat.active ? "Active" : "Inactive"}</small></p>) : <p>No demat account yet.</p>}<h3>Bank Accounts</h3>{banks.filter((bank) => bank.owner === focusedInvestor.id).map((bank) => <p key={bank.id}>{bank.is_placeholder ? "Bank details needed" : bank.bank_name} · {bank.account_masked} <small>{bank.active ? "Active" : "Inactive"}</small></p>)}<h3>UPIs</h3>{linkedAccounts[focusedInvestor.id]?.upis.length ? linkedAccounts[focusedInvestor.id].upis.map((upi) => <p key={upi.id}>{upi.handle_masked} <small>{upi.verified ? "Verified" : "Not verified"} · {upi.active ? "Active" : "Inactive"}</small></p>) : <p>No UPIs yet.</p>}</div>{focusedInvestor.active && <PreferredFunding key={focusedInvestor.id} workspaceId={workspace.id} investor={focusedInvestor} investors={activeInvestors} banks={banks.filter((bank) => bank.active)} initialPreferences={preferences[focusedInvestor.id] ?? []} canEdit={canEdit} />}</Drawer>}
      {showAddInvestor && <Drawer title="Add investor" onClose={() => setShowAddInvestor(false)}><form onSubmit={addInvestor} className="sign-in-form"><label htmlFor="investor-name">Name</label><input id="investor-name" required value={name} onChange={(event) => setName(event.target.value)} /><label htmlFor="investor-pan">PAN</label><input id="investor-pan" required maxLength={10} autoComplete="off" value={pan} onChange={(event) => setPan(event.target.value)} /><button type="submit" disabled={busy}>Add investor</button></form></Drawer>}
      {pendingRemoval && <ConfirmationDialog title={`Permanently delete ${pendingCount} ${pendingName}${pendingCount === 1 ? "" : "s"}?`} description={`These records cannot be restored. ${pendingRemoval.kind === "bank" || pendingRemoval.kind === "investor" ? "Bank balance history stays in Funds. Accounts linked to applications cannot be deleted." : "Records linked to applications cannot be deleted."} ${confirmationDetail}`} confirmLabel={`Delete ${pendingCount === 1 ? pendingName : "selected"}`} busy={busy} onCancel={() => setPendingRemoval(null)} onConfirm={() => void updateItems(pendingRemoval.kind, pendingRemoval.ids, "delete")} />}
      {verifyUpiId && <ConfirmationDialog title="Verify UPI ID?" description="Confirm that you checked the UPI ID, its holder and its real bank account. This allows the payment method to be used in planning once the bank is active." confirmLabel="Mark verified" busy={busy} onCancel={() => setVerifyUpiId(null)} onConfirm={() => void verifyUpi()} />}
    </>}
  </div></main>;
}
