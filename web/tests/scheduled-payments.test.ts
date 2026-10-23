import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ScheduledPayments from "../src/app/funds/scheduled-payments";

test("all-bank payments retain bank identity alongside each payment", () => {
  const page = renderToStaticMarkup(createElement(ScheduledPayments, {
    workspaceId: "scope", bankId: "", canEdit: true,
    banks: [{ id: "bank-a", label: "Synthetic A" }, { id: "bank-b", label: "Synthetic B" }],
    initialPayments: ["a", "b"].map((id) => ({ id, bank_id: `bank-${id}`, name: `EMI ${id}`, amount: "100", frequency: "MONTHLY" as const, start_date: "2026-10-23", next_due_date: "2026-11-23", end_date: null, active: true })),
  }));
  assert.match(page, /Synthetic A/);
  assert.match(page, /Synthetic B/);
  assert.match(page, /Edit EMI a/);
  assert.match(page, /Edit EMI b/);
});
