"use client";

import { FormEvent, useEffect, useState } from "react";
import { ConfirmationDialog } from "@/components/confirmation-dialog";
import { Drawer } from "@/components/drawer";
import { EmptyState, PageHeader, SectionHeading, StatusBadge } from "@/components/ui";
import { formatInr } from "@/lib/money";
import { movePriority, sortByPriority } from "@/lib/priorities";
import { reassignBankUpis } from "@/lib/bank-ownership";
import { applySettingsAction, toggleSelected, type SettingsKind } from "@/lib/settings-removal";
import PreferredFunding, { type BankOption, type FundingPreference } from "./preferred-funding";
import AccountImport from "./account-import";

type Workspace = { id: string; name: string; role: string };
type Investor = { id: string; name: string; pan_masked: string; pan_display: string; planning_priority: number; active: boolean; payment_ready: boolean; payment_hint: string };
type Demat = { id: string; depository: string; dp_id_masked: string; client_id_masked: string; client_id_display: string; broker: string; active: boolean };
type Upi = { id: string; holder: string; bank_id: string; handle: string; active: boolean; verified: boolean };
type LinkedAccounts = Record<string, { demats: Demat[]; upis: Upi[] }>;
type Tab = "investors" | "demats" | "banks" | "upis" | "import";
type AddAccountKind = "demat" | "bank" | "upi";
type Selection = Record<SettingsKind, string[]>;
type AccountRow = { id: string; name: string; owner: string; detail: string; active: boolean; isPlaceholder?: boolean; statusLabel?: string };
const emptySelection = (): Selection => ({ investor: [], demat: [], bank: [], upi: [] });

async function accountError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null) as Record<string, unknown> | null;
  if (typeof body?.detail === "string") return body.detail;
  if (typeof body?.message === "string") return body.message;
  const messages = (value: unknown): string[] => typeof value === "string" ? [value] : Array.isArray(value) ? value.flatMap(messages) : value && typeof value === "object" ? Object.values(value).flatMap(messages) : [];
  return messages(body)[0] ?? fallback;
}

const labelForKind: Record<SettingsKind, string> = {
  investor: "investor",
  demat: "demat account",
  bank: "bank account",
  upi: "UPI",
};

function AccountTable({
  title, kind, rows, selected, canEdit, busy, onToggle, onSelectAll, onAction, onAdd, onEdit, addLabel, addDisabled, addDisabledReason,
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
  addDisabledReason?: string;
}) {
  const visible = [...new Map(rows.map((row) => [row.id, row])).values()].sort((a, b) => Number(b.active) - Number(a.active));
  const selectedActive = visible.filter((row) => row.active && selected.includes(row.id)).map((row) => row.id);
  const selectedInactive = visible.filter((row) => !row.active && !row.isPlaceholder && selected.includes(row.id)).map((row) => row.id);
  return <section className="settings-account-group" aria-label={title}>
    <SectionHeading title={title} action={canEdit && <div className="settings-section-actions"><span title={addDisabled ? addDisabledReason : undefined}><button type="button" className="button-secondary" disabled={busy || addDisabled} onClick={onAdd}>+ {addLabel}</button></span>{visible.length > 0 && <><button type="button" className="button-secondary" disabled={busy} onClick={() => onSelectAll(kind, visible.map((row) => row.id), !visible.every((row) => selected.includes(row.id)))}>{visible.every((row) => selected.includes(row.id)) ? "Clear selection" : "Select all"}</button>{selectedActive.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAction(kind, selectedActive, "deactivate")}>Deactivate selected ({selectedActive.length})</button>}{selectedInactive.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAction(kind, selectedInactive, "activate")}>Activate selected ({selectedInactive.length})</button>}{selected.length > 0 && <button type="button" className="button-danger" disabled={busy} onClick={() => onAction(kind, selected, "delete")}>Delete selected ({selected.length})</button>}</>}</div>} />
    {visible.length === 0 ? <div className="settings-account-empty">No {kind === "upi" ? "UPI IDs" : title.toLowerCase()} added yet.</div> : <div className="settings-table-wrap"><table className="settings-table"><thead><tr>
      {canEdit && <th scope="col" className="settings-select-cell"><label><input type="checkbox" aria-label={`Select all ${title.toLowerCase()}`} checked={visible.every((row) => selected.includes(row.id))} disabled={busy} onChange={(event) => onSelectAll(kind, visible.map((row) => row.id), event.target.checked)} /></label></th>}
      <th scope="col">{kind === "bank" ? "Account Number" : "Account"}</th><th scope="col">Investor</th><th scope="col">Details</th><th scope="col">Status</th><th scope="col">Action</th>
    </tr></thead><tbody>{visible.map((row) => <tr key={row.id} className={row.active ? "" : "settings-inactive-row"}>
      {canEdit && <td data-label="Select" className="settings-select-cell"><label><input type="checkbox" aria-label={`Select ${row.name}`} checked={selected.includes(row.id)} disabled={busy} onChange={(event) => onToggle(kind, row.id, event.target.checked)} /></label></td>}
      <th scope="row" data-label={kind === "bank" ? "Account Number" : "Account"}>{row.name}</th><td data-label="Investor">{row.owner}</td><td data-label="Details">{row.detail}</td><td data-label="Status"><StatusBadge tone={row.statusLabel ? "warning" : row.active ? "positive" : row.isPlaceholder ? "warning" : "neutral"}>{row.statusLabel ?? (row.isPlaceholder ? "Needs details" : row.active ? "Active" : "Inactive")}</StatusBadge></td>
      <td data-label="Action">{canEdit ? <div className="settings-row-actions">{onEdit && <button type="button" className="button-secondary" disabled={busy} onClick={() => onEdit(row.id)}>{row.isPlaceholder ? "Complete details" : "Edit"}</button>}{!row.isPlaceholder && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAction(kind, [row.id], row.active ? "deactivate" : "activate")}>{row.active ? "Deactivate" : "Activate"}</button>}<button type="button" className="button-ghost-danger" disabled={busy} onClick={() => onAction(kind, [row.id], "delete")}>Delete</button></div> : "—"}</td>
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
  const workspace = initialWorkspace;
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
  const [editDepository, setEditDepository] = useState<"CDSL" | "NSDL">("CDSL");
  const [editDpId, setEditDpId] = useState("");
  const [editClientId, setEditClientId] = useState("");
  const [editBroker, setEditBroker] = useState("");
  const [editBankId, setEditBankId] = useState<string | null>(null);
  const [editBankOwner, setEditBankOwner] = useState("");
  const [editBankName, setEditBankName] = useState("");
  const [editAccountNumber, setEditAccountNumber] = useState("");
  const [editUpiId, setEditUpiId] = useState<string | null>(null);
  const [editUpiHolder, setEditUpiHolder] = useState("");
  const [editUpiBankId, setEditUpiBankId] = useState("");
  const [editUpiHandle, setEditUpiHandle] = useState("");
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
  const [name, setName] = useState("");
  const [pan, setPan] = useState("");
  const [includeNewDemat, setIncludeNewDemat] = useState(false);
  const [includeNewBank, setIncludeNewBank] = useState(false);
  const [includeNewUpi, setIncludeNewUpi] = useState(false);
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!workspace?.id) return;
    try {
      const key = `lotneeti-import-success:${workspace.id}`;
      const imported = sessionStorage.getItem(key);
      if (imported) {
        sessionStorage.removeItem(key);
        queueMicrotask(() => { setMessage(imported); setTab("investors"); });
      }
    } catch { /* The page still works when browser storage is unavailable. */ }
  }, [workspace?.id]);
  const canEdit = workspace?.role !== "VIEWER";
  const activeInvestors = sortByPriority(investors.filter((investor) => investor.active));
  const investorsWithoutDemat = activeInvestors.filter((investor) => !linkedAccounts[investor.id]?.demats.length);
  const visibleInvestors = [...activeInvestors, ...sortByPriority(investors.filter((investor) => !investor.active))];
  const selectedActiveInvestors = visibleInvestors.filter((investor) => investor.active && selected.investor.includes(investor.id)).map((investor) => investor.id);
  const selectedInactiveInvestors = visibleInvestors.filter((investor) => !investor.active && selected.investor.includes(investor.id)).map((investor) => investor.id);
  const focusedInvestor = investors.find((investor) => investor.id === selectedInvestor);
  const investorName = (id: string) => investors.find((item) => item.id === id)?.name ?? "Deleted investor";
  const dematRows = Object.entries(linkedAccounts).flatMap(([owner, accounts]) => accounts.demats.map((demat) => ({
    id: demat.id, name: `${demat.depository} · ${demat.client_id_display}`, owner: investorName(owner),
    detail: demat.broker || "Broker not set", active: demat.active,
  })));
  const bankRows = banks.map((bank) => ({
    id: bank.id, name: `${bank.bank_name || "BANK"} · ${bank.account_display}`, owner: bank.is_placeholder ? "Choose owner" : investorName(bank.owner),
    detail: `Balance ${formatInr(bank.current_balance)}${bank.effective_cross_funding_policy === "DISALLOW" ? " · Own account only" : ""}`, active: bank.active, isPlaceholder: bank.is_placeholder,
    statusLabel: bank.is_placeholder ? "Choose owner" : undefined,
  }));
  const upiRows = Object.values(linkedAccounts).flatMap((accounts) => accounts.upis.map((upi) => {
    const bank = banks.find((item) => item.id === upi.bank_id);
    const holder = investors.find((item) => item.id === upi.holder);
    return {
      id: upi.id, name: upi.handle, owner: bank?.is_placeholder ? "Choose holder" : investorName(upi.holder),
      detail: bank?.is_placeholder ? "BANK · choose owner" : bank?.bank_name || "BANK", active: upi.active,
      statusLabel: upi.active ? (bank?.is_placeholder ? "Choose owner" : !bank?.active ? "Bank inactive" : !holder?.active ? "Investor inactive" : undefined) : undefined,
    };
  }));

  function note(text: string, error = false) {
    setMessage(text);
    setMessageError(error);
  }

  async function refreshInvestors() {
    if (!workspace) return;
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/investors`);
      if (response.ok) setInvestors(sortByPriority(await response.json() as Investor[]));
    } catch {
      // A refresh failure must not turn a successful account update into an error.
    }
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

  async function addInvestor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/investors/setup`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name, pan, planning_priority: Math.max(0, ...investors.map((item) => item.planning_priority)) + 1,
          ...(includeNewDemat ? { demat: { depository, dp_id: dpId, client_id: clientId, broker } } : {}),
          ...(includeNewBank ? { bank: { bank_name: bankName, account_number: accountNumber, initial_balance: openingBalance, ...(includeNewUpi ? { upi_handle: upiHandle } : {}) } } : {}),
        }),
      });
      if (!response.ok) throw new Error(await accountError(response, "Check the investor and account details and try again."));
      try { sessionStorage.setItem(`lotneeti-import-success:${workspace.id}`, "Investor and selected accounts added."); } catch { /* The save succeeded. */ }
      window.location.reload();
    } catch (error) {
      note(error instanceof Error ? error.message : "Check the investor and account details and try again.", true);
    } finally { setBusy(false); }
  }

  function openAddInvestor() {
    setName(""); setPan("");
    setIncludeNewDemat(false); setIncludeNewBank(false); setIncludeNewUpi(false);
    setDepository("CDSL"); setDpId(""); setClientId(""); setBroker("");
    setBankName(""); setAccountNumber(""); setOpeningBalance("0"); setUpiHandle("");
    setShowAddInvestor(true);
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

  async function openEditBank(id: string) {
    const bank = banks.find((item) => item.id === id);
    if (!workspace || !bank) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks/${id}`);
      if (!response.ok) throw new Error(await accountError(response, "Could not load the bank details."));
      const detail = await response.json() as BankOption & { account_number: string };
      const matchingInvestors = investors.filter((investor) => investor.payment_hint === detail.account_reference);
      setEditBankOwner(detail.is_placeholder ? matchingInvestors.length === 1 ? matchingInvestors[0].id : "" : detail.owner);
      setEditBankName(detail.bank_name || "BANK");
      setEditAccountNumber(detail.account_number);
      setEditBankId(id);
    } catch (error) { note(error instanceof Error ? error.message : "Could not load the bank details.", true); }
    finally { setBusy(false); }
  }

  async function openEditDemat(id: string) {
    if (!workspace) return;
    const ownerId = Object.entries(linkedAccounts).find(([, accounts]) => accounts.demats.some((item) => item.id === id))?.[0];
    if (!ownerId) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/investors/${ownerId}/demats/${id}`);
      if (!response.ok) throw new Error(await accountError(response, "Could not load the demat details."));
      const detail = await response.json() as Demat & { dp_id: string; client_id: string };
      setEditDepository(detail.depository as "CDSL" | "NSDL");
      setEditDpId(detail.dp_id);
      setEditClientId(detail.client_id);
      setEditBroker(detail.broker);
      setEditDematId(id);
    } catch (error) { note(error instanceof Error ? error.message : "Could not load the demat details.", true); }
    finally { setBusy(false); }
  }

  async function openEditUpi(id: string) {
    if (!workspace) return;
    const upi = Object.values(linkedAccounts).flatMap((accounts) => accounts.upis).find((item) => item.id === id);
    if (!upi) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks/${upi.bank_id}/upis/${id}`);
      if (!response.ok) throw new Error(await accountError(response, "Could not load the UPI details."));
      const detail = await response.json() as Upi;
      setEditUpiHolder(detail.holder);
      setEditUpiBankId(upi.bank_id);
      setEditUpiHandle(detail.handle);
      setEditUpiId(id);
    } catch (error) { note(error instanceof Error ? error.message : "Could not load the UPI details.", true); }
    finally { setBusy(false); }
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
        body: JSON.stringify({ depository: editDepository, dp_id: editDpId, client_id: editClientId, broker: editBroker }),
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
        body: JSON.stringify({ owner: editBankOwner, bank_name: editBankName, account_number: editAccountNumber, ...(banks.find((bank) => bank.id === editBankId)?.is_placeholder ? { active: true } : {}) }),
      });
      if (!response.ok) throw new Error(await accountError(response, "Check the bank details and try again."));
      const updated = await response.json() as BankOption;
      setBanks((current) => current.map((item) => item.id === updated.id ? updated : item));
      setLinkedAccounts((current) => reassignBankUpis(current, updated.id, updated.owner));
      await refreshInvestors();
      setEditBankId(null);
      note(updated.active ? "Bank details saved." : "Bank details saved. Activate this bank when you are ready to use it.");
    } catch (error) {
      note(error instanceof Error ? error.message : "Check the bank details and try again.", true);
    } finally { setBusy(false); }
  }

  async function saveUpi(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !editUpiId) return;
    const upi = Object.values(linkedAccounts).flatMap((accounts) => accounts.upis).find((item) => item.id === editUpiId);
    if (!upi) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks/${upi.bank_id}/upis/${upi.id}`, {
        method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ holder: editUpiHolder, bank_id: editUpiBankId, handle: editUpiHandle }),
      });
      if (!response.ok) throw new Error(await accountError(response, "Check the UPI details and try again."));
      const saved = await response.json() as Upi;
      setLinkedAccounts((current) => {
        const next = Object.fromEntries(Object.entries(current).map(([id, accounts]) => [id, {
          ...accounts, upis: accounts.upis.filter((item) => item.id !== upi.id),
        }]));
        const holderAccounts = next[saved.holder] ?? { demats: [], upis: [] };
        next[saved.holder] = { ...holderAccounts, upis: [...holderAccounts.upis, { ...saved, bank_id: editUpiBankId }] };
        return next;
      });
      await refreshInvestors();
      setEditUpiId(null);
      note("UPI details saved.");
    } catch (error) {
      note(error instanceof Error ? error.message : "We could not save this UPI.", true);
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
      note("UPI added.");
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
        throw new Error(await accountError(response, "We could not change these items. Please try again."));
      }
      const next = applySettingsAction({ investors, banks, linkedAccounts }, kind, ids, action);
      setInvestors(next.investors);
      setBanks(next.banks);
      setLinkedAccounts(next.linkedAccounts);
      if (kind === "bank" || kind === "upi") {
        await refreshInvestors();
      }
      setSelected(emptySelection());
      if (action === "delete") {
        const deleted = new Set(ids);
        setPreferences((current) => Object.fromEntries(Object.entries(current)
          .filter(([investorId]) => kind !== "investor" || !deleted.has(investorId))
          .map(([investorId, rows]) => [investorId, kind === "bank" ? rows.filter((row) => !deleted.has(row.bank)) : rows])));
      }
      if (kind === "investor" && selectedInvestor && ids.includes(selectedInvestor)) setSelectedInvestor(null);
      note(`${ids.length} ${labelForKind[kind]}${ids.length === 1 ? "" : "s"} ${action === "delete" ? kind === "investor" ? "removed from Investors" : "permanently deleted" : action === "activate" ? "activated" : "deactivated"}.`);
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
  const confirmationDetail = pendingRemoval?.kind === "bank"
    ? "Bank balance history stays in Funds."
    : "";

  return <main className="page settings-page"><div className="shell settings-shell">
    <PageHeader eyebrow="Account" title="Settings" description="Manage your investors and linked accounts." />
    {message && <p role={messageError ? "alert" : "status"} className={messageError ? "settings-message error" : "settings-message"}>{message}</p>}
    {loadError ? <div className="plan-error" role="alert">Settings could not be loaded. <button type="button" className="button-secondary" onClick={() => window.location.reload()}>Retry</button></div> : !workspace ? <EmptyState title="Your account is being set up" detail="Sign in again to finish your account setup." /> : <>
      <nav className="settings-tabs" aria-label="Settings sections">
        {([["investors", "Investors"], ["demats", "Demat Accounts"], ["banks", "Bank Accounts"], ["upis", "UPIs"], ["import", "Import"]] as const).map(([key, label]) => <button key={key} type="button" className={tab === key ? "settings-tab active" : "settings-tab"} aria-current={tab === key ? "page" : undefined} onClick={() => changeTab(key)}>{label}</button>)}
      </nav>
      {tab === "investors" && <section aria-label="Investors">
        <SectionHeading title="Investors" detail="Active investors are planned first. Inactive investors stay visible here." action={canEdit && <div className="settings-section-actions">
          {visibleInvestors.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => selectAll("investor", visibleInvestors.map((investor) => investor.id), !visibleInvestors.every((investor) => selected.investor.includes(investor.id)))}>{visibleInvestors.every((investor) => selected.investor.includes(investor.id)) ? "Clear selection" : "Select all"}</button>}
          {selectedActiveInvestors.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => itemAction("investor", selectedActiveInvestors, "deactivate")}>Deactivate selected ({selectedActiveInvestors.length})</button>}
          {selectedInactiveInvestors.length > 0 && <button type="button" className="button-secondary" disabled={busy} onClick={() => itemAction("investor", selectedInactiveInvestors, "activate")}>Activate selected ({selectedInactiveInvestors.length})</button>}
          {selected.investor.length > 0 && <button type="button" className="button-danger" disabled={busy} onClick={() => itemAction("investor", selected.investor, "delete")}>Delete selected ({selected.investor.length})</button>}
          <button type="button" className="button-secondary" disabled={busy || activeInvestors.length === 0} onClick={() => void savePriority()}>Save priority</button><button type="button" onClick={openAddInvestor}>+ Add investor</button>
        </div>} />
        {visibleInvestors.length === 0 ? <EmptyState title="No investors yet" detail="Add an investor to begin planning IPO applications." /> : <div className="settings-table-wrap"><table className="settings-table"><thead><tr>
          {canEdit && <th scope="col" className="settings-select-cell"><label><input type="checkbox" aria-label="Select all investors" checked={visibleInvestors.every((investor) => selected.investor.includes(investor.id))} disabled={busy} onChange={(event) => selectAll("investor", visibleInvestors.map((investor) => investor.id), event.target.checked)} /></label></th>}
          <th scope="col">Investor</th><th scope="col">PAN</th><th scope="col">Priority</th><th scope="col">Demat</th><th scope="col">Banks</th><th scope="col">UPIs</th><th scope="col">Status</th><th scope="col">Actions</th>
        </tr></thead><tbody>{visibleInvestors.map((investor, index) => <tr key={investor.id} className={investor.active ? "" : "settings-inactive-row"}>
          {canEdit && <td data-label="Select" className="settings-select-cell"><label><input type="checkbox" aria-label={`Select ${investor.name}`} checked={selected.investor.includes(investor.id)} disabled={busy} onChange={(event) => toggle("investor", investor.id, event.target.checked)} /></label></td>}
          <th scope="row" data-label="Investor">{investor.name}</th><td data-label="PAN">{investor.pan_display}</td>
          <td data-label="Priority">{!investor.active ? "—" : <div className="settings-priority"><input aria-label={`Priority for ${investor.name}`} type="number" min="1" value={investor.planning_priority} disabled={!canEdit || busy} onChange={(event) => setInvestors(investors.map((item) => item.id === investor.id ? { ...item, planning_priority: Math.max(1, Number(event.target.value)) } : item))} />{canEdit && <span className="settings-order"><button type="button" className="button-ghost" aria-label={`Move ${investor.name} up`} disabled={index === 0 || busy} onClick={() => setInvestors([...movePriority(activeInvestors, index, -1), ...investors.filter((item) => !item.active)])}>↑</button><button type="button" className="button-ghost" aria-label={`Move ${investor.name} down`} disabled={index === activeInvestors.length - 1 || busy} onClick={() => setInvestors([...movePriority(activeInvestors, index, 1), ...investors.filter((item) => !item.active)])}>↓</button></span>}</div>}</td>
          <td data-label="Demat">{linkedAccounts[investor.id]?.demats.filter((item) => item.active).length ?? 0}</td>
          <td data-label="Banks">{banks.filter((bank) => bank.owner === investor.id && bank.active).length}</td>
          <td data-label="UPIs">{linkedAccounts[investor.id]?.upis.filter((item) => item.active).length ?? 0}</td>
          <td data-label="Status"><StatusBadge tone={!investor.active ? "neutral" : investor.payment_ready ? "positive" : "warning"}>{!investor.active ? "Inactive" : investor.payment_ready ? "Active" : "Payment needed"}</StatusBadge></td>
          <td data-label="Actions" className="settings-row-actions"><button type="button" className="button-secondary" onClick={() => setSelectedInvestor(investor.id)}>View</button>{canEdit && <><button type="button" className="button-secondary" disabled={busy} onClick={() => itemAction("investor", [investor.id], investor.active ? "deactivate" : "activate")}>{investor.active ? "Deactivate" : "Activate"}</button><button type="button" className="button-ghost-danger" disabled={busy} onClick={() => itemAction("investor", [investor.id], "delete")}>Delete</button></>}</td>
        </tr>)}</tbody></table></div>}
      </section>}

      {tab === "demats" && <AccountTable title="Demat Accounts" kind="demat" rows={dematRows} selected={selected.demat} canEdit={canEdit} busy={busy} onToggle={toggle} onSelectAll={selectAll} onAction={itemAction} onAdd={() => openAddAccount("demat")} onEdit={(id) => void openEditDemat(id)} addLabel="Add demat" addDisabled={investorsWithoutDemat.length === 0} addDisabledReason={activeInvestors.length === 0 ? "Add or activate an investor first." : "Every investor has a linked demat account."} />}
      {tab === "banks" && <AccountTable title="Bank Accounts" kind="bank" rows={bankRows} selected={selected.bank} canEdit={canEdit} busy={busy} onToggle={toggle} onSelectAll={selectAll} onAction={itemAction} onAdd={() => openAddAccount("bank")} onEdit={(id) => void openEditBank(id)} addLabel="Add bank" addDisabled={activeInvestors.length === 0} addDisabledReason="Add or activate an investor first." />}
      {tab === "upis" && <AccountTable title="UPIs" kind="upi" rows={upiRows} selected={selected.upi} canEdit={canEdit} busy={busy} onToggle={toggle} onSelectAll={selectAll} onAction={itemAction} onAdd={() => openAddAccount("upi")} onEdit={(id) => void openEditUpi(id)} addLabel="Add UPI" addDisabled={activeInvestors.length === 0 || banks.every((bank) => !bank.active)} addDisabledReason={activeInvestors.length === 0 ? "Add or activate an investor first." : "Complete and activate a bank account first."} />}

      {tab === "import" && <AccountImport workspaceId={workspace.id} canEdit={canEdit} investors={investors} />}
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
        <label htmlFor="edit-depository">Depository</label><select id="edit-depository" value={editDepository} onChange={(event) => setEditDepository(event.target.value as "CDSL" | "NSDL")}><option value="CDSL">CDSL</option><option value="NSDL">NSDL</option></select>
        <label htmlFor="edit-dp-id">DP ID</label><input id="edit-dp-id" required={editDepository === "NSDL"} value={editDpId} onChange={(event) => setEditDpId(event.target.value)} />
        <label htmlFor="edit-client-id">Client ID</label><input id="edit-client-id" required value={editClientId} onChange={(event) => setEditClientId(event.target.value)} />
        <label htmlFor="edit-broker">Broker</label><input id="edit-broker" value={editBroker} onChange={(event) => setEditBroker(event.target.value)} />
        <button type="submit" disabled={busy}>Save demat</button>
      </form></Drawer>}
      {editBankId && <Drawer title={banks.find((bank) => bank.id === editBankId)?.is_placeholder ? "Choose bank account owner" : "Edit bank account"} onClose={() => setEditBankId(null)}><form className="sign-in-form" onSubmit={saveBank}>
        {(banks.find((bank) => bank.id === editBankId)?.is_placeholder || banks.find((bank) => bank.id === editBankId)?.is_imported_reference) && <p className="form-note">This account uses the UPI ID as its account number. You can replace it with the real bank account number now or later.</p>}
        <p className="form-note">Saving the bank holder also updates every UPI linked to this bank.</p>
        <label htmlFor="edit-bank-owner">Bank and UPI holder</label><select id="edit-bank-owner" value={editBankOwner} onChange={(event) => setEditBankOwner(event.target.value)} required><option value="">Choose holder</option>{investors.filter((investor) => investor.active || investor.id === editBankOwner).map((investor) => <option key={investor.id} value={investor.id}>{investor.name}{investor.active ? "" : " (inactive)"}</option>)}</select>
        <label htmlFor="edit-bank-name">Bank name</label><input id="edit-bank-name" required value={editBankName} onChange={(event) => setEditBankName(event.target.value)} />
        <label htmlFor="edit-bank-number">Account number</label><input id="edit-bank-number" required autoComplete="off" value={editAccountNumber} onChange={(event) => setEditAccountNumber(event.target.value)} />
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
        <label htmlFor="upi-bank">Bank account</label><select id="upi-bank" value={upiBankId} onChange={(event) => setUpiBankId(event.target.value)} required>{banks.filter((bank) => bank.active).map((bank) => <option key={bank.id} value={bank.id}>{bank.bank_name} · {bank.account_display}</option>)}</select>
        <label htmlFor="upi-handle">UPI ID</label><input id="upi-handle" required autoComplete="off" placeholder="name@provider" value={upiHandle} onChange={(event) => setUpiHandle(event.target.value)} />
        <button type="submit" disabled={busy}>Add UPI</button>
      </form></Drawer>}
      {editUpiId && <Drawer title="Edit UPI" onClose={() => setEditUpiId(null)}><form className="sign-in-form" onSubmit={saveUpi}>
        <label htmlFor="edit-upi-holder">Investor</label><select id="edit-upi-holder" value={editUpiHolder} onChange={(event) => setEditUpiHolder(event.target.value)} required>{investors.filter((investor) => investor.active || investor.id === editUpiHolder).map((investor) => <option key={investor.id} value={investor.id}>{investor.name}{investor.active ? "" : " (inactive)"}</option>)}</select>
        <label htmlFor="edit-upi-bank">Bank account</label><select id="edit-upi-bank" value={editUpiBankId} onChange={(event) => setEditUpiBankId(event.target.value)} required>{banks.filter((bank) => bank.active || bank.id === editUpiBankId).map((bank) => <option key={bank.id} value={bank.id}>{bank.bank_name || "BANK"} · {bank.account_display}</option>)}</select>
        <label htmlFor="edit-upi-handle">UPI ID</label><input id="edit-upi-handle" required autoComplete="off" value={editUpiHandle} onChange={(event) => setEditUpiHandle(event.target.value)} />
        <button type="submit" disabled={busy}>Save UPI</button>
      </form></Drawer>}
      {focusedInvestor && <Drawer title={focusedInvestor.name} onClose={() => setSelectedInvestor(null)}><div className="settings-investor-detail"><p><strong>PAN</strong><span>{focusedInvestor.pan_display}</span></p><p><strong>Status</strong><StatusBadge tone={!focusedInvestor.active ? "neutral" : focusedInvestor.payment_ready ? "positive" : "warning"}>{!focusedInvestor.active ? "Inactive" : focusedInvestor.payment_ready ? "Active" : "Payment needed"}</StatusBadge></p>{!focusedInvestor.payment_ready && <p><strong>UPI reference</strong><span>{focusedInvestor.payment_hint} · Complete and activate the linked bank before planning.</span></p>}</div><div className="settings-linked"><h3>Demat Account</h3>{linkedAccounts[focusedInvestor.id]?.demats.length ? linkedAccounts[focusedInvestor.id].demats.map((demat) => <p key={demat.id}>{demat.depository} · {demat.dp_id_masked} / {demat.client_id_display} <small>{demat.broker} · {demat.active ? "Active" : "Inactive"}</small></p>) : <p>No demat account yet.</p>}<h3>Bank Accounts</h3>{banks.filter((bank) => bank.owner === focusedInvestor.id).map((bank) => <p key={bank.id}>{bank.bank_name || "BANK"} · {bank.account_display} <small>{bank.active ? "Active" : "Inactive"}</small></p>)}<h3>UPIs</h3>{linkedAccounts[focusedInvestor.id]?.upis.length ? linkedAccounts[focusedInvestor.id].upis.map((upi) => <p key={upi.id}>{upi.handle} <small>{upi.verified ? "Ready" : "Not ready"} · {upi.active ? "Active" : "Inactive"}</small></p>) : <p>No UPIs yet.</p>}</div>{focusedInvestor.active && <PreferredFunding key={focusedInvestor.id} workspaceId={workspace.id} investor={focusedInvestor} investors={activeInvestors} banks={banks.filter((bank) => bank.active)} initialPreferences={preferences[focusedInvestor.id] ?? []} canEdit={canEdit} />}</Drawer>}
      {showAddInvestor && <Drawer title="Add investor" onClose={() => setShowAddInvestor(false)}><form onSubmit={addInvestor} className="sign-in-form"><label htmlFor="investor-name">Name</label><input id="investor-name" required value={name} onChange={(event) => setName(event.target.value)} /><label htmlFor="investor-pan">PAN</label><input id="investor-pan" required maxLength={10} autoComplete="off" value={pan} onChange={(event) => setPan(event.target.value)} /><p className="intro">Add linked accounts now, or add them later in Settings.</p>
        <label htmlFor="investor-add-demat">Demat account</label><select id="investor-add-demat" value={includeNewDemat ? "yes" : "no"} onChange={(event) => setIncludeNewDemat(event.target.value === "yes")}><option value="no">Add later</option><option value="yes">Add now</option></select>
        {includeNewDemat && <><label htmlFor="investor-depository">Depository</label><select id="investor-depository" value={depository} onChange={(event) => setDepository(event.target.value as "CDSL" | "NSDL")}><option value="CDSL">CDSL</option><option value="NSDL">NSDL</option></select>{depository === "NSDL" && <><label htmlFor="investor-dpid">DP ID</label><input id="investor-dpid" required value={dpId} onChange={(event) => setDpId(event.target.value)} /></>}<label htmlFor="investor-client-id">Client ID</label><input id="investor-client-id" required value={clientId} onChange={(event) => setClientId(event.target.value)} /><label htmlFor="investor-broker">Broker (optional)</label><input id="investor-broker" value={broker} onChange={(event) => setBroker(event.target.value)} /></>}
        <label htmlFor="investor-add-bank">Bank account</label><select id="investor-add-bank" value={includeNewBank ? "yes" : "no"} onChange={(event) => { const add = event.target.value === "yes"; setIncludeNewBank(add); if (!add) setIncludeNewUpi(false); }}><option value="no">Add later</option><option value="yes">Add now</option></select>
        {includeNewBank && <><label htmlFor="investor-bank-name">Bank name</label><input id="investor-bank-name" required value={bankName} onChange={(event) => setBankName(event.target.value)} /><label htmlFor="investor-account-number">Account number</label><input id="investor-account-number" required autoComplete="off" value={accountNumber} onChange={(event) => setAccountNumber(event.target.value)} /><label htmlFor="investor-opening-balance">Opening Balance (₹)</label><input id="investor-opening-balance" type="number" min="0" step="0.01" required value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} /><label htmlFor="investor-add-upi">UPI ID</label><select id="investor-add-upi" value={includeNewUpi ? "yes" : "no"} onChange={(event) => setIncludeNewUpi(event.target.value === "yes")}><option value="no">Add later</option><option value="yes">Add now</option></select>{includeNewUpi && <><label htmlFor="investor-upi-id">UPI ID</label><input id="investor-upi-id" required autoComplete="off" placeholder="name@provider" value={upiHandle} onChange={(event) => setUpiHandle(event.target.value)} /></>}</>}
        <button type="submit" disabled={busy}>{busy ? "Adding…" : "Add investor"}</button></form></Drawer>}
      {pendingRemoval && <ConfirmationDialog title={pendingRemoval.kind === "investor" ? `Delete ${pendingCount} ${pendingName}${pendingCount === 1 ? "" : "s"}?` : `Permanently delete ${pendingCount} ${pendingName}${pendingCount === 1 ? "" : "s"}?`} description={pendingRemoval.kind === "investor" ? "The investor will leave the Investors list. Linked accounts will be deactivated, while application and balance history stay available." : `These records cannot be restored. Records linked to applications cannot be deleted. ${confirmationDetail}`} confirmLabel={`Delete ${pendingCount === 1 ? pendingName : "selected"}`} busy={busy} onCancel={() => setPendingRemoval(null)} onConfirm={() => void updateItems(pendingRemoval.kind, pendingRemoval.ids, "delete")} />}
    </>}
  </div></main>;
}
