import assert from "node:assert/strict";
import { test } from "node:test";
import { estimatedSaleCharges, indiaSaleDate, unsoldShares } from "../src/lib/sale-defaults";

test("NSE delivery estimate reproduces the supplied ₹13,655 itemized bill", () => {
  assert.deepEqual(estimatedSaleCharges("1365.50", 10), {
    turnover: "13655.00", brokerage: "0.00", dp: "15.34", stt: "13.66",
    exchange: "0.47", sebi: "0.01", gst: "0.09", stamp: "0.00", total: "29.57",
  });
});

test("charges scale with price and quantity, round each fee to paise and do not tax DP twice", () => {
  assert.equal(estimatedSaleCharges("1000", 10)?.total, "25.76");
  assert.equal(estimatedSaleCharges("1000", 20)?.total, "36.18");
  assert.equal(estimatedSaleCharges("0.01", 1)?.total, "15.34");
  assert.equal(estimatedSaleCharges("100.01", 100)?.turnover, "10001.00");
});

test("invalid or incomplete sale terms do not generate a charge estimate", () => {
  for (const price of ["", "0", "-1", "abc", "Infinity", "1.001"]) assert.equal(estimatedSaleCharges(price, 1), null);
  for (const quantity of [0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) assert.equal(estimatedSaleCharges("100", quantity), null);
});

test("default sale quantity is the remaining allotment and never includes another application", () => {
  const sales = [{ application: "own", quantity: 4 }, { application: "other", quantity: 50 }];
  assert.equal(unsoldShares("own", 12, []), 12);
  assert.equal(unsoldShares("own", 12, sales), 8);
  assert.equal(unsoldShares("own", 2, sales), 0);
  assert.equal(unsoldShares("own", null, []), 0);
});

test("default sale date uses India midnight independently of workstation time zone", () => {
  assert.equal(indiaSaleDate(new Date("2026-10-27T18:29:59Z")), "2026-10-27");
  assert.equal(indiaSaleDate(new Date("2026-10-27T18:30:00Z")), "2026-10-28");
});
