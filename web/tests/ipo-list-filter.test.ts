import assert from "node:assert/strict";
import test from "node:test";
import { matchesIPOFilters } from "../src/app/ipos/ipo-list-filter";

const rows = [
  { issuer: "Alpha Steel", status: "OPEN", issueType: "MAINBOARD", selected: true, skipped: false },
  { issuer: "Beta Tech", status: "UPCOMING", issueType: "SME", selected: false, skipped: true },
  { issuer: "Gamma Labs", status: "CLOSED", issueType: "SME", selected: false, skipped: false },
];

test("status, type and choice filters combine, while choices within a group can be combined", () => {
  assert.deepEqual(rows.filter((row) => matchesIPOFilters(row, "", ["open", "upcoming"], ["sme"], ["selected", "skipped"])).map((row) => row.issuer), ["Beta Tech"]);
  assert.deepEqual(rows.filter((row) => matchesIPOFilters(row, "", ["open", "upcoming"], [], ["selected", "skipped"])).map((row) => row.issuer), ["Alpha Steel", "Beta Tech"]);
});

test("search filters immediately from the current text and empty groups mean all", () => {
  assert.deepEqual(rows.filter((row) => matchesIPOFilters(row, " ga ", [], [], [])).map((row) => row.issuer), ["Gamma Labs"]);
  assert.deepEqual(rows.filter((row) => matchesIPOFilters(row, "", ["closed"], [], [])).map((row) => row.issuer), ["Gamma Labs"]);
});
