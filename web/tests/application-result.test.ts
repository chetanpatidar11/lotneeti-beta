import assert from "node:assert/strict";
import { test } from "node:test";
import { applicationResultAmount, defaultAllotmentShares, validAllotmentAmount } from "../src/lib/application-result";
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

test("category defaults use IPO lot size and bHNI defaults to the minimum sHNI lots", () => {
  const terms = { category: "RETAIL", lots: 5, lot_size: 12, upper_price: "1700.00", max_quantity: 60 };
  assert.equal(defaultAllotmentShares(terms), 12);
  assert.equal(defaultAllotmentShares({ ...terms, category: "SHNI", lots: 17, max_quantity: 204 }), 204);
  assert.equal(defaultAllotmentShares({ ...terms, category: "BHNI", lots: 50, max_quantity: 600 }), 120);
  assert.equal(defaultAllotmentShares({ ...terms, category: "SHARE" }), null);
  assert.equal(defaultAllotmentShares({ ...terms, category: "BHNI", upper_price: "invalid" }), null);
  assert.equal(defaultAllotmentShares({ ...terms, category: "BHNI", max_quantity: 12 }), null);
  assert.equal(defaultAllotmentShares({ ...terms, category: "BHNI", lot_size: 100, upper_price: "1000.00", max_quantity: 1100 }), 300);
});

test("manual amounts may differ from upper-band cost but must fit the blocked funds", () => {
  assert.equal(validAllotmentAmount("19900.50", "20400.00"), true);
  for (const amount of ["", "0", "-1", "20400.01", "1.234", "invalid"]) {
    assert.equal(validAllotmentAmount(amount, "20400.00"), false);
  }
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
