"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { balanceActionLabel, formatInr } from "@/lib/money";
import { Drawer } from "@/components/drawer";
import { EmptyState, PageHeader, SectionHeading, StatusBadge } from "@/components/ui";
import ScheduledPayments, { type ScheduledPayment } from "./scheduled-payments";

type Workspace = { id: string; name: string; role: string };
type Investor = { id: string; name: string };
type Bank = { id: string; owner: string; bank_name: string; account_masked: string; account_reference: string; current_balance: string; active: boolean };
type Change = { id: number; operation: "ADD" | "REMOVE" | "SET" | "ALLOTMENT"; amount: string; balance: string; note: string; created_at: string };
type StatementChange = Change & { bank_id: string; bank_name: string; owner_name: string; account_masked: string; delta: string };
type StatementPage = { results: StatementChange[]; next_page: number | null; total: number };
type CapitalLine = { balance: string; blocked: string; planned: string; available: string };
type ArchivedBank = { id: string; bank_name: string; account_masked: string; last_changed: string };
type Action = "add" | "remove" | "set";
type Tab = "accounts" | "statement" | "payments" | "deleted";
const actionLabel = (action: Action) => balanceActionLabel(action.toUpperCase() as "ADD" | "REMOVE" | "SET");

export default function FundsScreen({ workspace, investors, initialBanks, statementBanks, initialPayments, capitalByBank, archivedBanks }: {
  workspace: Workspace; investors: Investor[]; initialBanks: Bank[]; statementBanks: Bank[];
  initialPayments: ScheduledPayment[];
  capitalByBank: Record<string, CapitalLine>; archivedBanks: ArchivedBank[];
}) {
  const [tab, setTab] = useState<Tab>("accounts");
  const [banks, setBanks] = useState(initialBanks);
  const [capitalLines, setCapitalLines] = useState(capitalByBank);
  const [paymentBankId, setPaymentBankId] = useState(initialBanks[0]?.id ?? "");
  const [statementBankId, setStatementBankId] = useState("");
  const [statement, setStatement] = useState<StatementChange[]>([]);
  const [statementNext, setStatementNext] = useState<number | null>(null);
  const [statementTotal, setStatementTotal] = useState(0);
  const [statementLoading, setStatementLoading] = useState(false);
  const [statementVersion, setStatementVersion] = useState(0);
  const statementRequest = useRef(0);
  const [archivedBankId, setArchivedBankId] = useState("");
  const [archivedChanges, setArchivedChanges] = useState<Change[]>([]);
  const [action, setAction] = useState<Action | null>(null);
  const [actionBankId, setActionBankId] = useState("");
  const [addBankOpen, setAddBankOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [name, setName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [ownerId, setOwnerId] = useState(investors[0]?.id ?? "");
  const [openingBalance, setOpeningBalance] = useState("0");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const actionBank = banks.find((bank) => bank.id === actionBankId);
  const statementBankChoices = [...statementBanks, ...banks.filter((bank) => !statementBanks.some((item) => item.id === bank.id))];
  const canEdit = workspace.role !== "VIEWER";
  const accountLabel = (bank: Bank) => `${bank.bank_name} · ${investors.find((item) => item.id === bank.owner)?.name ?? "Owner"} · ${bank.account_reference || bank.account_masked}`;

  async function refreshCapital() {
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/capital`);
      if (response.ok) {
        const capital = await response.json() as { by_bank?: Record<string, CapitalLine> };
        setCapitalLines(capital.by_bank ?? {});
      }
    } catch { /* The saved balance remains visible if totals are briefly unavailable. */ }
  }

  const loadStatement = useCallback(async (bankId: string, page: number, append: boolean) => {
    const requestId = ++statementRequest.current;
    setStatementLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page) });
      if (bankId) params.set("bank", bankId);
      const response = await fetch(`/api/workspaces/${workspace.id}/balance-statement?${params}`);
      if (!response.ok) throw new Error();
      const result = await response.json() as StatementPage;
      if (requestId !== statementRequest.current) return;
      setStatement((current) => append ? [...current, ...result.results] : result.results);
      setStatementNext(result.next_page);
      setStatementTotal(result.total);
    } catch {
      if (requestId === statementRequest.current) setMessage("Bank statement could not be loaded. Please try again.");
    } finally {
      if (requestId === statementRequest.current) setStatementLoading(false);
    }
  }, [workspace.id]);

  useEffect(() => {
    if (tab === "statement") queueMicrotask(() => { void loadStatement(statementBankId, 1, false); });
  }, [tab, statementBankId, statementVersion, loadStatement]);

  async function loadArchivedHistory(bankId: string) {
    setArchivedBankId(bankId);
    const response = await fetch(`/api/workspaces/${workspace.id}/banks/${bankId}/balance-changes`);
    if (response.ok) setArchivedChanges((await response.json()) as Change[]);
    else setMessage("Deleted bank history could not be loaded. Try again.");
  }

  async function createBank(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ owner: ownerId, bank_name: name, account_number: accountNumber, initial_balance: openingBalance }) });
      if (!response.ok) throw new Error();
      const bank = await response.json() as Bank;
      setBanks((current) => [...current, bank]);
      if (!paymentBankId) setPaymentBankId(bank.id);
      await refreshCapital();
      setName(""); setAccountNumber(""); setOpeningBalance("0"); setAddBankOpen(false); setMessage("Bank added.");
    } catch { setMessage("Check the bank details and try again."); }
    finally { setBusy(false); }
  }

  async function changeBalance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!actionBank || !action) return;
    setBusy(true); setMessage("");
    try {
      const response = await fetch(`/api/workspaces/${workspace.id}/banks/${actionBank.id}/balance-changes/${action}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ amount }) });
      if (!response.ok) {
        const result = await response.json().catch(() => ({})) as { detail?: string | string[] } | string[];
        const detail = Array.isArray(result) ? result.join(" ") : Array.isArray(result.detail) ? result.detail.join(" ") : result.detail;
        throw new Error(detail || "Check the amount and bank details, then try again.");
      }
      const result = await response.json() as { balance: string };
      setBanks((current) => current.map((bank) => bank.id === actionBank.id ? { ...bank, current_balance: result.balance } : bank));
      await refreshCapital();
      setAmount(""); setAction(null); setActionBankId(""); setStatementVersion((value) => value + 1);
      setMessage("Balance updated.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Check the amount and try again."); }
    finally { setBusy(false); }
  }

  return <main className="page"><div className="shell settings-shell">
    <PageHeader eyebrow="Capital / Funds" title="Bank availability" description={workspace.name} action={canEdit && investors.length > 0 ? <button type="button" onClick={() => setAddBankOpen(true)}>+ Add bank</button> : undefined} />
    {message && <p className="plan-note" role="status">{message}</p>}
    <nav className="settings-tabs funds-tabs" aria-label="Funds sections">
      {([["accounts", "Accounts"], ["statement", "Bank statement"], ["payments", "Scheduled Payments / EMI"], ["deleted", "Deleted bank history"]] as const).map(([key, label]) => <button type="button" key={key} className={tab === key ? "settings-tab active" : "settings-tab"} aria-current={tab === key ? "page" : undefined} onClick={() => setTab(key)}>{label}</button>)}
    </nav>
    {tab === "accounts" && <>
      {canEdit && banks.length > 0 && <div className="funds-actions" role="group" aria-label="Balance actions">{(["add", "remove", "set"] as Action[]).map((item) => <button key={item} className={item === "add" ? "" : "button-secondary"} type="button" onClick={() => { setAction(item); setActionBankId(""); setAmount(""); }}>{actionLabel(item)}</button>)}</div>}
      {banks.length === 0 ? <EmptyState title="No active bank accounts" detail={investors.length === 0 ? "Add or activate an investor, then link a bank." : "Add a bank or activate an account in Settings."} action={<Link href="/settings/investors">Investor settings</Link>} /> :
        <div className="compact-table-wrap funds-table-wrap"><table className="compact-table funds-table"><thead><tr><th>Owner / bank</th><th>Balance</th><th>Blocked</th><th>Planned</th><th>Available</th><th>State</th></tr></thead><tbody>{banks.map((bank) => { const line = capitalLines[bank.id]; return <tr key={bank.id}><th scope="row" className="funds-owner-cell"><strong>{bank.bank_name}</strong><span>{investors.find((item) => item.id === bank.owner)?.name ?? "Owner"} · {bank.account_reference || bank.account_masked}</span></th><td>{formatInr(bank.current_balance)}</td><td>{line ? formatInr(line.blocked) : "—"}</td><td>{line ? formatInr(line.planned) : "—"}</td><td className="positive-cell">{line ? formatInr(line.available) : "—"}</td><td><StatusBadge tone={bank.active ? "positive" : "neutral"}>{bank.active ? "Active" : "Paused"}</StatusBadge></td></tr>; })}</tbody></table></div>}
    </>}
    {tab === "statement" && <section className="section-panel funds-statement"><SectionHeading title="Bank statement" detail={`${statementTotal} recorded movement${statementTotal === 1 ? "" : "s"} across your banks`} />
      <label className="funds-filter">Bank account<select value={statementBankId} onChange={(event) => setStatementBankId(event.target.value)}><option value="">All banks</option>{statementBankChoices.map((bank) => <option key={bank.id} value={bank.id}>{bank.bank_name} · {bank.account_reference || bank.account_masked}</option>)}</select></label>
      {statement.length === 0 && !statementLoading ? <EmptyState title="No balance changes yet." /> : <div className="compact-table-wrap"><table className="compact-table funds-statement-table"><thead><tr><th>Date</th><th>Bank / owner</th><th>Transaction</th><th>Debit</th><th>Credit</th><th>Balance after</th></tr></thead><tbody>{statement.map((change) => <tr key={change.id}><td>{new Date(change.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</td><th scope="row"><strong>{change.bank_name}</strong><span>{change.owner_name} · {change.account_masked}</span></th><td>{balanceActionLabel(change.operation)}{change.note && <small>{change.note}</small>}</td><td>{Number(change.delta) < 0 ? formatInr(Math.abs(Number(change.delta))) : "—"}</td><td>{Number(change.delta) > 0 ? formatInr(change.delta) : "—"}</td><td>{formatInr(change.balance)}</td></tr>)}</tbody></table></div>}
      {statementNext && <button type="button" className="button-secondary" disabled={statementLoading} onClick={() => void loadStatement(statementBankId, statementNext, true)}>{statementLoading ? "Loading…" : "Load more"}</button>}
    </section>}
    {tab === "payments" && <section className="section-panel funds-scheduled"><SectionHeading title="Scheduled Payments / EMI" detail="Upcoming debits for the selected bank" />
      {banks.length === 0 ? <EmptyState title="Add a bank to schedule payments." /> : <><label className="funds-filter">Bank account<select value={paymentBankId} onChange={(event) => setPaymentBankId(event.target.value)}>{banks.map((bank) => <option key={bank.id} value={bank.id}>{accountLabel(bank)}</option>)}</select></label><ScheduledPayments key={paymentBankId} workspaceId={workspace.id} bankId={paymentBankId} canEdit={canEdit} initialPayments={paymentBankId === initialBanks[0]?.id ? initialPayments : []} /></>}
    </section>}
    {tab === "deleted" && <section className="section-panel archived-bank-history" aria-label="Deleted bank history"><SectionHeading title="Deleted bank history" detail="Balance changes remain available after a bank is deleted." />
      {archivedBanks.length === 0 ? <EmptyState title="No deleted bank history." /> : <div className="settings-funding-list">{archivedBanks.map((bank) => <button key={bank.id} type="button" className="settings-funding-row" aria-pressed={archivedBankId === bank.id} onClick={() => void loadArchivedHistory(bank.id)}><span><strong>{bank.bank_name}</strong><small>{bank.account_masked}</small></span><span>View history</span></button>)}</div>}
      {archivedBankId && <ul className="change-list">{archivedChanges.map((change) => <li key={change.id}><span><strong>{balanceActionLabel(change.operation)}</strong><br /><small>{new Date(change.created_at).toLocaleDateString("en-IN", { dateStyle: "medium" })}</small></span><span>{formatInr(change.amount)}<br /><small>Balance {formatInr(change.balance)}</small></span></li>)}</ul>}
    </section>}
    {action && <Drawer title={actionLabel(action)} onClose={() => { setAction(null); setActionBankId(""); }}><form onSubmit={changeBalance} className="sign-in-form"><label htmlFor="balance-bank">Bank account</label><select id="balance-bank" value={actionBankId} required onChange={(event) => setActionBankId(event.target.value)}><option value="">Choose a bank account</option>{banks.map((bank) => <option key={bank.id} value={bank.id}>{accountLabel(bank)}</option>)}</select>{actionBank && <p className="intro">Current balance: <strong>{formatInr(actionBank.current_balance)}</strong></p>}<label htmlFor="balance-amount">{action === "set" ? "New balance" : "Amount"} (₹)</label><input id="balance-amount" type="number" min={action === "set" ? "0" : "0.01"} step="0.01" required value={amount} onChange={(event) => setAmount(event.target.value)} /><button type="submit" disabled={busy || !actionBank}>{actionLabel(action)}</button></form></Drawer>}
    {addBankOpen && <Drawer title="Add bank account" onClose={() => setAddBankOpen(false)}><form onSubmit={createBank} className="sign-in-form"><label htmlFor="bank-owner">Owner</label><select id="bank-owner" value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>{investors.map((investor) => <option key={investor.id} value={investor.id}>{investor.name}</option>)}</select><label htmlFor="bank-name">Bank name</label><input id="bank-name" required value={name} onChange={(event) => setName(event.target.value)} /><label htmlFor="account-number">Account number</label><input id="account-number" required autoComplete="off" value={accountNumber} onChange={(event) => setAccountNumber(event.target.value)} /><label htmlFor="opening-balance">Opening Balance (₹)</label><input id="opening-balance" type="number" min="0" step="0.01" required value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} /><button type="submit" disabled={busy}>Add bank</button></form></Drawer>}
  </div></main>;
}
