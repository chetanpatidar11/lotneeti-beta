import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import FundsScreen from "../src/app/funds/funds-screen";

test("Funds shows the complete UPI, bank totals, and the newer account tools", () => {
  const bank = { id: "bank-1", owner: "investor-1", bank_name: "Demo Bank", account_masked: "••••0001", account_reference: "", account_display: "SYNTHETIC0001", current_balance: "50000.00", active: true, linked_upis: ["full.synthetic.handle@exampleupi"] };
  const page = renderToStaticMarkup(createElement(FundsScreen, {
    workspace: { id: "scope-1", name: "Private", role: "OWNER" },
    investors: [{ id: "investor-1", name: "Synthetic Investor" }], initialBanks: [bank], statementBanks: [bank], initialPayments: [], archivedBanks: [],
    capitalByBank: { "bank-1": { balance: "50000", blocked: "15000", planned: "10000", available: "25000" } },
  }));
  assert.match(page, /full.synthetic.handle@exampleupi/);
  assert.match(page, /<tfoot>/);
  assert.match(page, /₹50,000/);
  assert.match(page, /₹25,000/);
  assert.match(page, /Transfer/);
  assert.match(page, /Deleted bank history/);
  assert.match(page, /Bank statement/);
});

test("Funds total Available nets an over-assigned bank against other balances", () => {
  const bank = { owner: "investor-1", bank_name: "Synthetic Bank", account_masked: "••••0001", account_reference: "", account_display: "SYNTHETIC0001", active: true, linked_upis: [] };
  const banks = [{ ...bank, id: "a", current_balance: "1000000.00" }, { ...bank, id: "b", current_balance: "1179101.00" }];
  const page = renderToStaticMarkup(createElement(FundsScreen, {
    workspace: { id: "scope-1", name: "Private", role: "OWNER" },
    investors: [{ id: "investor-1", name: "Synthetic Investor" }], initialBanks: banks, statementBanks: banks, initialPayments: [], archivedBanks: [],
    capitalByBank: {
      a: { balance: "1000000.00", blocked: "1204527.00", planned: "0.00", available: "0.00" },
      b: { balance: "1179101.00", blocked: "876813.00", planned: "0.00", available: "302288.00" },
    },
  }));
  const footer = page.match(/<tfoot>(.*?)<\/tfoot>/)?.[1] ?? "";
  assert.match(footer, /₹21,79,101/);
  assert.match(footer, /₹20,81,340/);
  assert.match(footer, /₹97,761/);
  assert.doesNotMatch(footer, /₹3,02,288/);
});
