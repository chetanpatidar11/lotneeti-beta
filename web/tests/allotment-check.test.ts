import assert from "node:assert/strict";
import { test } from "node:test";
import { checkedAmount, initialCheckedDraft, validCheckedDraft } from "../src/lib/allotment-check";

const item = { upper_price: "100.01", max_quantity: 150, amount: "15001.50", lot_size: 150 };
const bid = { quantity: 73, applied: 150, reference: "SYNTHETIC-1", demat: "", category: "RETAIL" };

test("checked quantities come from the registrar, not category defaults, with exact paise", () => {
  const draft = initialCheckedDraft(item, [bid], 0);
  assert.equal(draft.quantity, "73");
  assert.equal(draft.cost, "7300.73");
  assert.equal(draft.selected, false);
  assert.equal(validCheckedDraft(item, draft, 0), true);
  assert.equal(validCheckedDraft(item, { ...draft, cost: "7200.50" }, 0), true);
});

test("failed and ambiguous lookups stay blank until a verified manual result is entered", () => {
  const draft = initialCheckedDraft(item, [bid], null);
  assert.equal(draft.quantity, "");
  assert.equal(draft.cost, "");
  assert.equal(validCheckedDraft(item, draft, null), false);
  const zero = { ...draft, quantity: "0", cost: "0.00" };
  assert.equal(validCheckedDraft(item, zero, null), false);
  assert.equal(validCheckedDraft(item, { ...zero, manualVerified: true }, null), true);
  assert.equal(validCheckedDraft(item, { ...zero, cost: "100", manualVerified: true }, null), false);
});

test("switching bid identity requires manual verification; invalid quantities and costs fail", () => {
  const draft = initialCheckedDraft(item, [bid, bid], 0);
  assert.equal(validCheckedDraft(item, { ...draft, sourceIndex: "1" }, 0), false);
  assert.equal(validCheckedDraft(item, { ...draft, sourceIndex: "1", manualVerified: true }, 0), true);
  for (const quantity of ["", "-1", "1.5", "151", "NaN"]) {
    assert.equal(checkedAmount(item, quantity), "");
    assert.equal(validCheckedDraft(item, { ...draft, quantity }, 0), false);
  }
  assert.equal(checkedAmount(item, "0"), "0.00");
  for (const cost of ["", "0", "-1", "15001.51", "1.234"]) assert.equal(validCheckedDraft(item, { ...draft, cost }, 0), false);
});
