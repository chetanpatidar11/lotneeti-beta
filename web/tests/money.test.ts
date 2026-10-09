import assert from "node:assert/strict";
import { test } from "node:test";
import { balanceActionLabel, formatInr } from "../src/lib/money";

test("bank amounts use Indian grouping and plain balance action labels", () => {
  assert.equal(formatInr("128400.00"), "₹1,28,400");
  assert.equal(formatInr("14985.00"), "₹14,985");
  assert.equal(formatInr("209790.00"), "₹2,09,790");
  assert.equal(formatInr("128400.50"), "₹1,28,400.50");
  assert.equal(balanceActionLabel("ADD"), "+ Add Money");
  assert.equal(balanceActionLabel("REMOVE"), "- Remove Money");
  assert.equal(balanceActionLabel("SET"), "Set Balance");
  assert.equal(balanceActionLabel("ALLOTMENT"), "Allotment cost");
});
