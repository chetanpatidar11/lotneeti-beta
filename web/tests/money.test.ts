import assert from "node:assert/strict";
import { test } from "node:test";
import { availableInr, balanceActionLabel, formatInr, sumInr } from "../src/lib/money";

test("bank amounts use Indian grouping and plain balance action labels", () => {
  assert.equal(formatInr("128400.00"), "₹1,28,400");
  assert.equal(formatInr("14985.00"), "₹14,985");
  assert.equal(formatInr("209790.00"), "₹2,09,790");
  assert.equal(formatInr("128400.50"), "₹1,28,400.50");
  assert.equal(balanceActionLabel("ADD"), "+ Add Money");
  assert.equal(balanceActionLabel("REMOVE"), "- Remove Money");
  assert.equal(balanceActionLabel("SET"), "Set Balance");
  assert.equal(balanceActionLabel("ALLOTMENT"), "Allotment cost");
  assert.equal(balanceActionLabel("TRANSFER_OUT"), "Transfer to bank");
  assert.equal(balanceActionLabel("TRANSFER_IN"), "Transfer from bank");
});


test("bank totals sum decimal amounts exactly to paise", () => {
  assert.equal(sumInr(["0.10", "0.20", "1234.56", undefined]), 1234.86);
});

test("total available nets all commitments before clamping and preserves paise", () => {
  assert.equal(availableInr("2179101.00", "2081340.00", "0.00"), 97761);
  assert.equal(availableInr("0.30", "0.10", "0.10"), 0.1);
  assert.equal(availableInr("100.00", "150.00", "0.00"), 0);
});
