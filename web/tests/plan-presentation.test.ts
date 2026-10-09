import assert from "node:assert/strict";
import test from "node:test";
import { bankReasonSummary, canExportPlan, fundingLabel, issueMessage, lockedMappings, planStatus, rankedBanks, reviewedMappings, rowIssueMessages, rowStatus, selectableApplicants, selectableDemats, selectableUpis, splitPlanningSelections, type PlanRow } from "../src/lib/plan-presentation";

const row: PlanRow = {
  ipo: "synthetic-ipo",
  applicant: "synthetic-applicant",
  category: "RETAIL",
  lots: 1,
  amount: "15000.00",
  demat: "synthetic-demat",
  bank: "synthetic-bank",
  upi: "synthetic-upi",
  locked: false,
  warnings: [],
  blocking_reasons: [],
  reasons: [],
};

test("plan choices exclude closed IPOs and count unavailable selections", () => {
  assert.deepEqual(splitPlanningSelections([
    { ipo: "open", mode: "RETAIL_ONLY" },
    { ipo: "upcoming", mode: "CUSTOM" },
    { ipo: "closed", mode: "SHNI_PREFERRED" },
  ], { open: "OPEN", upcoming: "UPCOMING", closed: "CLOSED" }), {
    available: [
      { ipo: "open", mode: "RETAIL_ONLY" },
      { ipo: "upcoming", mode: "CUSTOM" },
    ],
    unavailableCount: 1,
  });
});

test("blocking status outranks a cross-funding warning", () => {
  assert.equal(rowStatus({ ...row, warnings: ["CROSS_FUNDING"] }), "Warning");
  assert.equal(rowStatus({ ...row, warnings: ["CROSS_FUNDING"], blocking_reasons: ["INSUFFICIENT_BALANCE"] }), "Blocking");
  assert.equal(rowStatus(row), "Ready");
});

test("funding label uses the planner warning", () => {
  assert.equal(fundingLabel(row), "Own bank");
  assert.equal(fundingLabel({ ...row, warnings: ["CROSS_FUNDING"] }), "Cross-funded");
});

test("automatic bank reasons use short safe copy and disappear on manual lock", () => {
  const automatic = { ...row, reasons: [
    { code: "OWN_WALLET_UNAVAILABLE", message: "Internal" },
    { code: "PREFERRED_CROSS_FUNDER", message: "Internal" },
    { code: "ROLLING_LIMIT_ROOM", message: "Internal" },
  ] };
  assert.deepEqual(bankReasonSummary(automatic), [
    "The applicant's own bank could not be used, so a preferred account was chosen.",
    "The bank and UPI have room for this application.",
  ]);
  assert.deepEqual(bankReasonSummary({ ...automatic, locked: true }), []);
  assert.deepEqual(bankReasonSummary({ ...row, reasons: [{ code: "UNKNOWN", message: "Internal" }] }), []);
});

test("demat choices include only active accounts for the applicant", () => {
  const options = selectableDemats({
    active: { label: "CDSL ••••001", applicant: "synthetic-applicant", active: true },
    paused: { label: "NSDL ••••002", applicant: "synthetic-applicant", active: false },
    other: { label: "CDSL ••••003", applicant: "other-applicant", active: true },
  }, "synthetic-applicant");
  assert.deepEqual(options, [{ id: "active", label: "CDSL ••••001" }]);
});

test("applicant choices include active workspace investors in priority order", () => {
  assert.deepEqual(selectableApplicants({
    second: { name: "Second", priority: 2, active: true },
    inactive: { name: "Inactive", priority: 1, active: false },
    first: { name: "First", priority: 1, active: true },
  }), [
    { id: "first", name: "First", priority: 1 },
    { id: "second", name: "Second", priority: 2 },
  ]);
});

test("bank choices rank own, preferred, then fallback and disable unusable banks", () => {
  const banks = {
    fallback: { label: "Fallback", owner: "other", balance: "30000.00", active: true, policy: "ALLOW" },
    preferred: { label: "Preferred", owner: "other", balance: "30000.00", active: true, policy: "ALLOW" },
    own: { label: "Own", owner: "synthetic-applicant", balance: "30000.00", active: true, policy: "DEFAULT" },
    forbidden: { label: "Forbidden", owner: "other", balance: "30000.00", active: true, policy: "DISALLOW" },
  };
  const upis = Object.fromEntries(Object.keys(banks).map((bank) => [bank, { label: bank, bank, holder: "synthetic-applicant", active: true, verified: true }]));
  const choices = rankedBanks(banks, upis, [{ bank: "preferred", priority: 1, enabled: true }], "synthetic-applicant");
  assert.deepEqual(choices.map((choice) => choice.id), ["own", "preferred", "fallback", "forbidden"]);
  assert.equal(choices.at(-1)?.disabled, true);
  assert.deepEqual(selectableUpis(upis, "own", "synthetic-applicant"), [{ id: "own", label: "own" }]);
});

test("cash and limit issues have plain row messages", () => {
  assert.deepEqual(rowIssueMessages({ ...row, blocking_reasons: ["CASH_OVERSPEND", "UPI_LIMIT_EXCEEDED"] }), [
    "This bank needs more available money.",
    "This UPI has reached its application limit.",
  ]);
});

test("only exact locked mapping fields enter the next planner run", () => {
  assert.deepEqual(lockedMappings([row, { ...row, locked: true, bank: "manual-bank" }]), [{
    ipo: row.ipo,
    applicant: row.applicant,
    category: row.category,
    lots: row.lots,
    amount: row.amount,
    demat: row.demat,
    bank: "manual-bank",
    upi: row.upi,
  }]);
});

test("blocking prevents export readiness while warnings remain visible", () => {
  const base = { status: "READY" as const, planned_total: "15000.00", rows: [row], audit_issues: [], uncovered: [] };
  assert.equal(planStatus(base), "Ready");
  assert.equal(canExportPlan(base), true);
  const warning = { ...base, rows: [{ ...row, warnings: ["CROSS_FUNDING"] }] };
  assert.equal(planStatus(warning), "Warning");
  assert.equal(canExportPlan(warning), true);
  assert.deepEqual(rowIssueMessages(warning.rows[0]), ["This application uses another person's funding account."]);
  const blocked = { ...warning, rows: [{ ...warning.rows[0], blocking_reasons: ["LOCKED_ROW_INFEASIBLE"] }] };
  assert.equal(planStatus(blocked), "Blocking");
  assert.equal(canExportPlan(blocked), false);
});

test("reviewed export rows keep edits and locks without display-only fields", () => {
  assert.deepEqual(reviewedMappings([{ ...row, amount: "210000.00", category: "SHNI", lots: 14, locked: true }]), [{
    ipo: row.ipo,
    applicant: row.applicant,
    category: "SHNI",
    lots: 14,
    amount: "210000.00",
    demat: row.demat,
    bank: row.bank,
    upi: row.upi,
    locked: true,
  }]);
});

test("validation issues use plain copy and unknown codes never leak", () => {
  assert.equal(issueMessage("INVALID_DEMAT"), "Choose an active demat for this applicant.");
  assert.equal(issueMessage("UNRECOGNIZED_INTERNAL_CODE"), "This application needs review before export.");
  assert.deepEqual(rowIssueMessages({ ...row, blocking_reasons: ["INVALID_AMOUNT", "UNKNOWN_CODE"] }), [
    "The amount does not match the chosen lots. Review the current IPO price.",
    "This application needs review before export.",
  ]);
});
