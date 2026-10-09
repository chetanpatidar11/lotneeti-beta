import assert from "node:assert/strict";
import { test } from "node:test";
import { applicationHistory, type ApplicationHistoryInput } from "../src/lib/application-history";

const blocked: ApplicationHistoryInput = {
  amount: "210000.00",
  status: "BLOCKED",
  planned_at: "2026-09-01T08:00:00Z",
  submitted_at: "2026-09-01T09:00:00Z",
  blocked_at: "2026-09-01T10:00:00Z",
  result_at: null,
  allotted_quantity: null,
  actual_cost: null,
};

test("partial allotment history shows actual debit and full block release", () => {
  const events = applicationHistory({ ...blocked, status: "ALLOTTED", result_at: "2026-09-08T10:00:00Z", allotted_quantity: 20, actual_cost: "42000.00" });
  assert.deepEqual(events.map((event) => event.label), [
    "Added to plan",
    "Submitted for ₹2,10,000",
    "₹2,10,000 blocked",
    "Allotted 20 shares",
    "₹42,000 deducted from Balance",
    "₹2,10,000 released from Blocked",
  ]);
});

test("not allotted history releases block without a debit", () => {
  const events = applicationHistory({ ...blocked, status: "NOT_ALLOTTED", result_at: "2026-09-08T10:00:00Z" });
  assert.equal(events.at(-1)?.label, "₹2,10,000 released from Blocked; Balance unchanged");
});
