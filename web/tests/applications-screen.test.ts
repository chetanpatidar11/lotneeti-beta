import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ApplicationsScreen, { type ApplicationItem } from "../src/app/applications/applications-screen";
import { savedApplicationNeedsReview } from "../src/lib/application-plan";

const item: ApplicationItem = {
  id: "application-1",
  plan_row_id: "plan-row-1",
  is_plan_row: false,
  ipo: "ipo-1",
  ipo_name: "Synthetic Industries",
  applicant: "synthetic-applicant",
  applicant_name: "Synthetic Investor",
  bank: "bank-1",
  bank_label: "Example Bank ••••0001",
  upi: "upi-1",
  upi_label: "••••@example",
  category: "RETAIL",
  lots: 1,
  max_quantity: 100,
  amount: "15000.00",
  status: "PLANNED",
  planned_at: "2026-09-28T10:00:00Z",
  submitted_at: null,
  blocked_at: null,
  result_at: null,
  edited_at: null,
  cancelled_at: null,
  allotted_quantity: null,
  actual_cost: null,
  close_date: "2026-10-03",
  allotment_date: "2026-10-08",
  sold_quantity: 0,
};

function render(status: ApplicationItem["status"], canEdit = true) {
  return renderToStaticMarkup(createElement(ApplicationsScreen, {
    workspaceId: "workspace-1",
    canEdit,
    initialItems: [{ ...item, status }],
    latestRun: { id: null, status: null },
  }));
}

test("applications require an IPO choice before showing rows and have no all-IPO option", () => {
  const page = render("PLANNED");
  assert.match(page, /Select an IPO above to view applications/);
  assert.match(page, /Select an IPO/);
  assert.doesNotMatch(page, /All IPOs/);
  assert.doesNotMatch(page, /Track latest plan/);
  assert.doesNotMatch(page, /Mark submitted/);
  assert.doesNotMatch(page, /Select all visible applications/);
  assert.doesNotMatch(render("PLANNED", false), /Mark submitted/);
});

test("IPO choices put the latest closing issue first", () => {
  const page = renderToStaticMarkup(createElement(ApplicationsScreen, {
    workspaceId: "workspace-1",
    canEdit: true,
    initialItems: [
      item,
      { ...item, id: "application-2", ipo: "ipo-2", ipo_name: "Newer Issue", close_date: "2026-10-20" },
      { ...item, id: "application-3", ipo: "ipo-3", ipo_name: "Middle Issue", close_date: "2026-10-12" },
    ],
    latestRun: { id: null, status: null },
  }));
  assert.ok(page.indexOf("Newer Issue") < page.indexOf("Middle Issue"));
  assert.ok(page.indexOf("Middle Issue") < page.indexOf("Synthetic Industries"));
});

test("saved blocked plans show a review message and retain their IPO choice", () => {
  const page = renderToStaticMarkup(createElement(ApplicationsScreen, {
    workspaceId: "workspace-1",
    canEdit: true,
    initialItems: [{ ...item, is_plan_row: true }],
    latestRun: { id: "blocked-plan", status: "BLOCKED" },
  }));
  assert.match(page, /Plan saved with warnings/);
  assert.match(page, /Your planned applications are shown below/);
  assert.match(page, /You can record submission, blocked funds, edits and cancellation without clearing the warnings/);
  assert.match(page, /href="\/plan"/);
  assert.match(page, /Synthetic Industries/);
  assert.doesNotMatch(page, /No planned applications yet/);
});

test("unready saved rows require review while tracked applications stay usable", () => {
  for (const status of ["BLOCKED", "CLEARED", null]) {
    assert.equal(savedApplicationNeedsReview(true, status), true);
    assert.equal(savedApplicationNeedsReview(false, status), false);
  }
  assert.equal(savedApplicationNeedsReview(true, "READY"), false);
  assert.equal(savedApplicationNeedsReview(false, "READY"), false);
});
