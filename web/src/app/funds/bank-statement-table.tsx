"use client";

import { useState } from "react";
import { Drawer } from "@/components/drawer";
import { bankIdentifiers } from "@/lib/bank-display";
import { balanceActionLabel, formatInr } from "@/lib/money";

export type StatementChange = {
  id: number;
  bank_id: string;
  bank_name: string;
  owner_name: string;
  account_masked: string;
  account_display: string;
  linked_upis: string[];
  operation: Parameters<typeof balanceActionLabel>[0];
  amount: string;
  delta: string;
  balance: string;
  note: string;
  counterparty_label: string;
  created_at: string;
};

function transactionLines(change: StatementChange) {
  const parts = change.counterparty_label.split(" · ");
  if (["TRANSFER_IN", "TRANSFER_OUT"].includes(change.operation) && parts.length >= 3) {
    const direction = change.operation === "TRANSFER_IN" ? "From" : "To";
    return {
      primary: `${direction} ${parts[0]} · ${parts[1]}`,
      secondary: [parts.slice(2).join(" · "), change.note].filter(Boolean).join(" · "),
    };
  }
  return {
    primary: balanceActionLabel(change.operation),
    secondary: [change.counterparty_label, change.note].filter(Boolean).join(" · ") || "—",
  };
}

export default function BankStatementTable({ changes }: { changes: StatementChange[] }) {
  const [selected, setSelected] = useState<StatementChange | null>(null);

  return <>
    <div className="compact-table-wrap statement-table-wrap">
      <table className="compact-table funds-statement-table" aria-label="Bank statement">
        <colgroup><col className="statement-date-column" /><col className="statement-bank-column" /><col className="statement-transaction-column" /><col className="statement-money-column" span={3} /></colgroup>
        <thead><tr><th scope="col">Date</th><th scope="col">Bank / owner</th><th scope="col">Transaction</th><th scope="col" className="statement-money">Debit</th><th scope="col" className="statement-money">Credit</th><th scope="col" className="statement-money">Balance</th></tr></thead>
        <tbody>{changes.map((change) => {
          const timestamp = new Date(change.created_at);
          const identifiers = bankIdentifiers(change.account_display ?? change.account_masked, change.linked_upis);
          const transaction = transactionLines(change);
          const debit = Number(change.delta) < 0 ? formatInr(Math.abs(Number(change.delta))) : "—";
          const credit = Number(change.delta) > 0 ? formatInr(change.delta) : "—";
          return <tr key={change.id}>
            <td><time dateTime={change.created_at} className="statement-lines"><span className="statement-primary">{timestamp.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</span><span className="statement-secondary">{timestamp.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}</span></time></td>
            <th scope="row"><div className="statement-lines"><span className="statement-primary" title={`${change.bank_name} · ${change.owner_name}`}><strong>{change.bank_name}</strong><span className="statement-owner"> · {change.owner_name}</span></span><span className="statement-secondary" title={identifiers}>{identifiers || "—"}</span></div></th>
            <td><div className="statement-transaction"><div className="statement-lines"><span className="statement-primary" title={transaction.primary}>{transaction.primary}</span><span className="statement-secondary" title={transaction.secondary}>{transaction.secondary}</span></div><button type="button" className="statement-details-button" aria-label={`View transaction details for ${change.bank_name}, ${change.owner_name}`} title="View full transaction details" onClick={() => setSelected(change)}>⋯</button></div></td>
            <td className="statement-money" data-label="Debit">{debit}</td><td className="statement-money" data-label="Credit">{credit}</td><td className="statement-money statement-balance" data-label="Balance">{formatInr(change.balance)}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
    {selected && <Drawer title="Transaction details" onClose={() => setSelected(null)}><dl className="statement-detail-list">
      <div><dt>Date</dt><dd>{new Date(selected.created_at).toLocaleString("en-IN", { dateStyle: "long", timeStyle: "short" })}</dd></div>
      <div><dt>Bank / owner</dt><dd>{selected.bank_name} · {selected.owner_name}</dd></div>
      <div><dt>Account / UPI</dt><dd>{bankIdentifiers(selected.account_display ?? selected.account_masked, selected.linked_upis)}</dd></div>
      <div><dt>Transaction</dt><dd>{balanceActionLabel(selected.operation)}</dd></div>
      {selected.counterparty_label && <div><dt>{selected.operation === "TRANSFER_IN" ? "From" : "To"}</dt><dd>{selected.counterparty_label}</dd></div>}
      {selected.note && <div><dt>Description</dt><dd>{selected.note}</dd></div>}
      <div><dt>Debit</dt><dd>{Number(selected.delta) < 0 ? formatInr(Math.abs(Number(selected.delta))) : "—"}</dd></div>
      <div><dt>Credit</dt><dd>{Number(selected.delta) > 0 ? formatInr(selected.delta) : "—"}</dd></div>
      <div><dt>Balance</dt><dd>{formatInr(selected.balance)}</dd></div>
    </dl></Drawer>}
  </>;
}
