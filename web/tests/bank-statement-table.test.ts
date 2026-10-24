import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import BankStatementTable, { type StatementChange } from "../src/app/funds/bank-statement-table";

const entry: StatementChange = {
  id: 1, bank_id: "synthetic-bank", bank_name: "Demo Bank", owner_name: "Synthetic Long Investor HUF",
  account_masked: "••••0001", account_display: "synthetic.owner@exampleupi", linked_upis: ["synthetic.owner@exampleupi"],
  operation: "ADD", amount: "35000", delta: "35000", balance: "379165", note: "Synthetic deposit note", counterparty_label: "", created_at: "2026-10-24T06:33:00Z",
};
function render(change: Partial<StatementChange>) {
  return renderToStaticMarkup(createElement(BankStatementTable, { changes: [{ ...entry, ...change }] }));
}
function amount(page: string, label: string) {
  return page.match(new RegExp(`<td[^>]*data-label="${label}"[^>]*>(.*?)</td>`))?.[1];
}

test("statement headers label signed debits, credits and the saved running balance", () => {
  for (const operation of ["ADD", "TRANSFER_IN", "SET"] as const) {
    const page = render({ operation });
    assert.equal(amount(page, "Debit"), "—");
    assert.equal(amount(page, "Credit"), "₹35,000");
    assert.equal(amount(page, "Balance"), "₹3,79,165");
  }
  for (const operation of ["REMOVE", "TRANSFER_OUT", "SET", "ALLOTMENT"] as const) {
    const page = render({ operation, delta: "-35000", balance: "7000" });
    assert.equal(amount(page, "Debit"), "₹35,000");
    assert.equal(amount(page, "Credit"), "—");
    assert.equal(amount(page, "Balance"), "₹7,000");
  }
  const unchanged = render({ operation: "SET", delta: "0" });
  assert.equal(amount(unchanged, "Debit"), "—");
  assert.equal(amount(unchanged, "Credit"), "—");
  assert.match(unchanged, /scope="col" class="statement-money">Balance<\/th>/);
  assert.doesNotMatch(unchanged, /Balance after/i);
});

test("transfer rows separate direction and owner from full UPI and note, with accessible details", () => {
  const page = render({ operation: "TRANSFER_IN", counterparty_label: "Second Bank · Synthetic Investor · full.synthetic.counterparty@exampleupi" });
  assert.match(page, /From Second Bank · Synthetic Investor/);
  assert.match(page, /full.synthetic.counterparty@exampleupi · Synthetic deposit note/);
  assert.match(page, /View transaction details for Demo Bank, Synthetic Long Investor HUF/);
});
