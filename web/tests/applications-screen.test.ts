import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ApplicationsScreen, { type ApplicationItem } from "../src/app/applications/applications-screen";

const item: ApplicationItem = {
  id: "application-1",
  ipo_name: "Synthetic Industries",
  applicant_name: "Synthetic Investor",
  bank_label: "Example Bank ••••0001",
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

test("application actions follow status and keep masked funding visible", () => {
  const planned = render("PLANNED");
  assert.match(planned, /Mark Submitted/);
  assert.doesNotMatch(planned, /Record Result/);
  assert.match(planned, /••••@example/);
  assert.match(render("SUBMITTED"), /Mark Blocked/);
  const blocked = render("BLOCKED");
  assert.match(blocked, /Record Result/);
  assert.doesNotMatch(blocked, /Mark Submitted/);
  assert.doesNotMatch(render("BLOCKED", false), /Record Result/);
});
