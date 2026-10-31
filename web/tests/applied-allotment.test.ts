import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { ApplicationItem } from "../src/app/applications/applications-screen";
import CheckAllotmentScreen from "../src/app/check-allotment/check-allotment-screen";
import { AllotmentResultRow } from "../src/app/check-allotment/allotment-checker";
import { appliedIpos } from "../src/lib/applied-ipos";
import { allotmentReviewRows } from "../src/lib/allotment-review";
import { initialCheckedDraft } from "../src/lib/allotment-check";

function application(change: Partial<ApplicationItem> = {}): ApplicationItem {
  return { id: "synthetic-app", plan_row_id: "synthetic-row", is_plan_row: false, ipo: "synthetic-ipo", ipo_name: "Synthetic Industries", applicant: "synthetic-investor", applicant_name: "Synthetic Investor", bank: "synthetic-bank", bank_label: "Synthetic Bank", upi: "synthetic-upi", upi_label: "synthetic@upi.test", close_date: "2026-10-24", allotment_date: "2026-10-28", sold_quantity: 0, category: "RETAIL", lots: 1, lot_size: 150, max_quantity: 150, upper_price: "100.00", amount: "15000.00", status: "BLOCKED", planned_at: "2026-10-20T10:00:00Z", submitted_at: "2026-10-22T10:00:00Z", blocked_at: "2026-10-22T10:01:00Z", result_at: null, edited_at: null, cancelled_at: null, allotted_quantity: null, actual_cost: null, ...change };
}

test("all applied IPOs include shareholder/public and completed/cancelled applied history, excluding unsubmitted plans", () => {
  const apps = [application(), application({ id: "share", category: "SHARE" }), application({ id: "old", ipo: "old", ipo_name: "Older Synthetic", close_date: "2026-10-01", status: "ALLOTTED" }), application({ id: "not", ipo: "old", ipo_name: "Older Synthetic", close_date: "2026-10-01", status: "NOT_ALLOTTED" }), application({ id: "cancelled", status: "CANCELLED" }), application({ id: "plan", ipo: "plan", status: "PLANNED", submitted_at: null }), application({ id: "saved", ipo: "saved", is_plan_row: true }), application({ id: "unsent-cancelled", ipo: "cancelled", status: "CANCELLED", submitted_at: null })];
  const summaries = appliedIpos(apps);
  assert.deepEqual(summaries.map((ipo) => ipo.id), ["synthetic-ipo", "old"]);
  assert.deepEqual([summaries[0].total, summaries[0].pending, summaries[0].cancelled], [3, 2, 1]);
  assert.deepEqual([summaries[1].allotted, summaries[1].notAllotted], [1, 1]);
});

test("all applied bids appear before a check, with blank unknown results and preserved completed results", () => {
  const apps = [application(), application({ id: "share", category: "SHARE" }), application({ id: "done", status: "ALLOTTED", allotted_quantity: 73, actual_cost: "7200.00" }), application({ id: "plan", status: "PLANNED", submitted_at: null })];
  const rows = allotmentReviewRows(apps, []);
  assert.equal(rows.length, 3);
  const unchecked = rows.find((row) => row.application.id === "synthetic-app")!;
  assert.equal(unchecked.state, "NOT_CHECKED");
  assert.equal(unchecked.check_available, false);
  assert.equal(unchecked.recorded_quantity, null);
  const draft = initialCheckedDraft(unchecked.application, unchecked.records, unchecked.matched_index);
  assert.equal(draft.quantity, "");
  assert.equal(draft.cost, "");
  const done = rows.find((row) => row.application.id === "done")!;
  assert.equal(done.recorded, true);
  assert.equal(done.recorded_quantity, 73);
  assert.equal(done.recorded_cost, "7200.00");
  const html = renderToStaticMarkup(createElement("table", null, createElement("tbody", null, createElement(AllotmentResultRow, { row: unchecked, draft, locked: true, onEdit: () => {} }))));
  assert.match(html, /Not checked/);
  assert.match(html, /disabled=""[^>]*aria-label="Record Synthetic Industries · Synthetic Investor Retail"|aria-label="Record Synthetic Industries · Synthetic Investor Retail"[^>]*disabled=""/);
  assert.equal((html.match(/<tr/g) ?? []).length, 1);
  assert.doesNotMatch(html, /fieldset|allotment-review-identity/);
});

test("the page lists all applied IPOs and grouped one-line bid rows by default with an optional single-IPO selector", () => {
  const items = [application(), application({ id: "second", ipo: "second-ipo", ipo_name: "Second Synthetic", status: "SUBMITTED" }), application({ id: "draft", ipo: "draft-ipo", ipo_name: "Unsubmitted Synthetic", submitted_at: null, status: "PLANNED" })];
  const html = renderToStaticMarkup(createElement(CheckAllotmentScreen, { workspaceId: "synthetic", canEdit: true, initialItems: items }));
  assert.match(html, /All applied IPOs/);
  assert.match(html, /Synthetic Industries/);
  assert.match(html, /Second Synthetic/);
  assert.doesNotMatch(html, /Unsubmitted Synthetic/);
  assert.match(html, /Check one IPO/);
  assert.match(html, /id="allotment-ipo-choice"/);
  assert.match(html, /<option[^>]*value=""[^>]*selected=""[^>]*>All applied IPOs<\/option>/);
  assert.match(html, /Applicant \/ Category/);
  for (const header of ["Registrar bid", "Lots", "Shares", "Amount (₹)", "Status", "Record"]) assert.ok(html.includes(header));
  assert.equal((html.match(/Not checked/g) ?? []).length, 2);
});

test("changing a matched bid requires verification and expired checks are labelled clearly", () => {
  const base = allotmentReviewRows([application()], [])[0];
  const row = { ...base, state: "FOUND", check_available: true, matched_index: 0, records: [{ quantity: 12, applied: 150, reference: "SYN-1", category: "RETAIL", demat: "" }, { quantity: 24, applied: 150, reference: "SYN-2", category: "SHARE", demat: "" }] };
  const draft = { ...initialCheckedDraft(row.application, row.records, 0), sourceIndex: "1" };
  const render = (value = row) => renderToStaticMarkup(createElement("table", null, createElement("tbody", null, createElement(AllotmentResultRow, { row: value, draft, locked: false, onEdit: () => {} }))));
  assert.match(render(), /Review bid/);
  assert.match(render(), /bid identity verified/);
  assert.doesNotMatch(render(), />Matched</);
  assert.match(render({ ...row, state: "EXPIRED" }), />Expired</);
});
