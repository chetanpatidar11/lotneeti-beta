"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { balanceActionLabel, formatInr } from "@/lib/money";
import { Drawer } from "@/components/drawer";
import { EmptyState, PageHeader, SectionHeading, StatusBadge } from "@/components/ui";
import ScheduledPayments, { type ScheduledPayment } from "./scheduled-payments";

type Workspace = { id: string; name: string; role: string };
type Investor = { id: string; name: string };
type Bank = { id: string; owner: string; bank_name: string; account_masked: string; current_balance: string; active: boolean };
type Change = { id: number; operation: "ADD" | "REMOVE" | "SET" | "ALLOTMENT"; amount: string; balance: string; note: string; created_at: string };
type CapitalLine = { balance: string; blocked: string; planned: string; available: string };
type Action = "add" | "remove" | "set";

export default function FundsScreen({ workspace, investors, initialBanks, initialChanges, initialPayments, capitalByBank }: {
  workspace: Workspace; investors: Investor[]; initialBanks: Bank[]; initialChanges: Change[];
  initialPayments: ScheduledPayment[]; capitalByBank: Record<string, CapitalLine>;
}) {
  const [banks, setBanks] = useState(initialBanks);
  const [selectedBankId, setSelectedBankId] = useState(initialBanks[0]?.id ?? "");
  const [changes, setChanges] = useState(initialChanges);
  const [action, setAction] = useState<Action | null>(null);
  const [addBankOpen, setAddBankOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [name, setName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [ownerId, setOwnerId] = useState(investors[0]?.id ?? "");
  const [openingBalance, setOpeningBalance] = useState("0");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const selectedBank = banks.find((bank) => bank.id === selectedBankId);
  const canEdit = workspace.role !== "VIEWER";

  async function loadHistory(bankId: string) {
    const response = await fetch(`/api/workspaces/${workspace.id}/banks/${bankId}/balance-changes`);
    if (response.ok) setChanges((await response.json()) as Change[]);
    else setMessage("Recent changes could not be loaded. Try selecting the bank again.");
  }
  async function createBank(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ owner: ownerId, bank_name: name, account_number: accountNumber, initial_balance: openingBalance }) });
      if (!response.ok) throw new Error();
      const bank = await response.json() as Bank;
      setBanks((current) => [...current, bank]); setSelectedBankId(bank.id);
      setName(""); setAccountNumber(""); setOpeningBalance("0"); setAddBankOpen(false);
      await loadHistory(bank.id); setMessage("Bank added.");
    } catch { setMessage("Check the bank details and try again."); }
    finally { setBusy(false); }
  }
  async function changeBalance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selectedBank || !action) return;
    setBusy(true); setMessage("");
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks/${selectedBank.id}/balance-changes/${action}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ amount }) });
      if (!response.ok) throw new Error();
      const result = await response.json() as { balance: string };
      setBanks((current) => current.map((bank) => bank.id === selectedBank.id ? { ...bank, current_balance: result.balance } : bank));
      setAmount(""); setAction(null); await loadHistory(selectedBank.id); setMessage("Balance updated. Refresh to see updated planning availability.");
    } catch { setMessage("Check the amount and try again."); }
    finally { setBusy(false); }
  }

  return <main className="page"><div className="shell settings-shell">
    <PageHeader eyebrow="Capital / Funds" title="Bank availability" description={workspace.name} action={canEdit && investors.length > 0 ? <button type="button" onClick={() => setAddBankOpen(true)}>+ Add bank</button> : undefined} />
    {message && <p className="plan-note" role="status">{message}</p>}
    {banks.length === 0 ? <EmptyState title="No active bank accounts" detail={investors.length === 0 ? "Add or restore an investor, then link a bank." : "Add a bank or restore a deleted account in Settings."} action={<Link href="/settings/investors">Investor settings</Link>} /> : <>
      <div className="compact-table-wrap funds-table-wrap"><table className="compact-table funds-table"><thead><tr><th>Owner / bank</th><th>Balance</th><th>Blocked</th><th>Planned</th><th>Available</th><th>State</th></tr></thead><tbody>{banks.map((bank) => { const line = capitalByBank[bank.id]; return <tr key={bank.id} className={selectedBankId === bank.id ? "selected-row" : ""}><th scope="row"><button className="bank-row-button" type="button" onClick={() => { setSelectedBankId(bank.id); void loadHistory(bank.id); }}>{bank.bank_name}<small>{investors.find((item) => item.id === bank.owner)?.name ?? "Owner"} · {bank.account_masked}</small></button></th><td>{formatInr(bank.current_balance)}</td><td>{line ? formatInr(line.blocked) : "—"}</td><td>{line ? formatInr(line.planned) : "—"}</td><td className="positive-cell">{line ? formatInr(line.available) : "—"}</td><td><StatusBadge tone={bank.active ? "positive" : "neutral"}>{bank.active ? "Active" : "Paused"}</StatusBadge></td></tr>; })}</tbody></table></div>
      {selectedBank && <><div className="funds-detail-bar"><div><span className="detail-label">Selected account</span><strong>{selectedBank.bank_name} · {selectedBank.account_masked}</strong></div>{canEdit && <div className="balance-actions" role="group" aria-label="Balance actions">{(["add", "remove", "set"] as Action[]).map((item) => <button key={item} className={item === "add" ? "" : "button-secondary"} type="button" onClick={() => setAction(item)}>{balanceActionLabel(item.toUpperCase() as "ADD" | "REMOVE" | "SET")}</button>)}</div>}</div>
        <div className="funds-bottom-grid"><section className="section-panel"><SectionHeading title="Scheduled Payments / EMI" detail="Upcoming debits from this bank" /><ScheduledPayments key={selectedBank.id} workspaceId={workspace.id} bankId={selectedBank.id} canEdit={canEdit} initialPayments={selectedBank.id === initialBanks[0]?.id ? initialPayments : []} /></section><section className="section-panel"><SectionHeading title="Recent balance changes" detail="Latest recorded movements" />{changes.length === 0 ? <EmptyState title="No balance changes yet." /> : <ul className="change-list">{changes.slice(0, 10).map((change) => <li key={change.id}><span><strong>{balanceActionLabel(change.operation)}</strong><br /><small>{new Date(change.created_at).toLocaleDateString("en-IN", { dateStyle: "medium" })}</small></span><span>{formatInr(change.amount)}<br /><small>Balance {formatInr(change.balance)}</small></span></li>)}</ul>}</section></div>
      </>}
    </>}
    {action && selectedBank && <Drawer title={`${balanceActionLabel(action.toUpperCase() as "ADD" | "REMOVE" | "SET")} · ${selectedBank.bank_name}`} onClose={() => setAction(null)}><p className="intro">Current Balance: {formatInr(selectedBank.current_balance)}</p><form onSubmit={changeBalance} className="sign-in-form"><label htmlFor="balance-amount">Amount (₹)</label><input id="balance-amount" type="number" min={action === "set" ? "0" : "0.01"} step="0.01" required value={amount} onChange={(event) => setAmount(event.target.value)} /><button type="submit" disabled={busy}>{balanceActionLabel(action.toUpperCase() as "ADD" | "REMOVE" | "SET")}</button></form></Drawer>}
    {addBankOpen && <Drawer title="Add bank account" onClose={() => setAddBankOpen(false)}><form onSubmit={createBank} className="sign-in-form"><label htmlFor="bank-owner">Owner</label><select id="bank-owner" value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>{investors.map((investor) => <option key={investor.id} value={investor.id}>{investor.name}</option>)}</select><label htmlFor="bank-name">Bank name</label><input id="bank-name" required value={name} onChange={(event) => setName(event.target.value)} /><label htmlFor="account-number">Account number</label><input id="account-number" required autoComplete="off" value={accountNumber} onChange={(event) => setAccountNumber(event.target.value)} /><label htmlFor="opening-balance">Opening Balance (₹)</label><input id="opening-balance" type="number" min="0" step="0.01" required value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} /><button type="submit" disabled={busy}>Add bank</button></form></Drawer>}
  </div></main>;
}
