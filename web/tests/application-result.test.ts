import assert from "node:assert/strict";
import { test } from "node:test";
import { applicationResultAmount } from "../src/lib/application-result";
import { newestApplicationFirst } from "../src/lib/application-order";

test("allotment uses the upper-band price with exact paise, including partial allotments", () => {
  assert.equal(applicationResultAmount("100.01", 73, 150), "7300.73");
  assert.equal(applicationResultAmount("100.01", 150, 150), "15001.50");
  for (const shares of [0, -1, 1.5, 151, NaN]) {
    assert.equal(applicationResultAmount("100.01", shares, 150), null);
  }
  assert.equal(applicationResultAmount("None", 1, 150), null);
  assert.equal(applicationResultAmount("0.00", 1, 150), null);
});

test("newest applications use submission time, planned fallback and stable ties", () => {
  const planned = "2026-10-23T10:00:00Z";
  const rows = [
    { id: "old", planned_at: planned, submitted_at: "2026-10-23T12:00:00Z" },
    { id: "new-b", planned_at: planned, submitted_at: "2026-10-25T12:00:00Z" },
    { id: "planned", planned_at: "2026-10-24T10:00:00Z", submitted_at: null },
    { id: "new-a", planned_at: planned, submitted_at: "2026-10-25T12:00:00Z" },
  ];
  assert.deepEqual([...rows].sort(newestApplicationFirst).map((row) => row.id), ["new-b", "new-a", "planned", "old"]);
  assert.equal(rows[0].id, "old");
});
