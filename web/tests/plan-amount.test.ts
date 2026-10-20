import assert from "node:assert/strict";
import test from "node:test";
import { amountForLots, minimumShniLots, peakConcurrentAmount, sumAmounts } from "../src/lib/plan-amount";

test("minimum sHNI lots is strictly above two lakh", () => {
  assert.equal(minimumShniLots("100.00", 150), 14);
  assert.equal(amountForLots("100.00", 150, 14), "210000.00");
  assert.equal(minimumShniLots("1500.00", 150), 1);
});

test("lot amount uses exact paise for manual changes", () => {
  assert.equal(amountForLots("101.25", 140, 3), "42525.00");
  assert.equal(amountForLots("100.01", 3, 2), "600.06");
  assert.throws(() => amountForLots("100.00", 150, 0));
  assert.equal(sumAmounts(["15000.00", "600.06"]), "15600.06");
});

test("draft peak excludes cash reused after an earlier allotment", () => {
  assert.equal(peakConcurrentAmount([
    { amount: "150000.00", closeDate: "2026-10-23", allotmentDate: "2026-10-26", category: "RETAIL" },
    { amount: "80000.00", closeDate: "2026-10-23", allotmentDate: "2026-10-26", category: "SHNI" },
    { amount: "100000.00", closeDate: "2026-10-29", allotmentDate: "2026-11-02", category: "RETAIL" },
  ]), "230000.00");
});
