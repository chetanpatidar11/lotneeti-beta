import assert from "node:assert/strict";
import test from "node:test";
import { amountForLots, minimumShniLots, sumAmounts } from "../src/lib/plan-amount";

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
