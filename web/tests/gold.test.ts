import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import GoldScreen from "../src/app/gold/gold-screen";
import { navigation } from "../src/app/app-nav";
import { filterGold, goldAmount, goldDate, goldError, goldGrams, goldPriceLabel, goldTimestamp, unavailableGoldReport, type GoldReport } from "../src/lib/gold";

const report: GoldReport = {
  market: { state: "UNAVAILABLE", source: "Gold API", source_url: "https://gold-api.com/", as_of: null, rates: {}, price_per_gram_24k: null },
  purchases: [{ price_mode: "MANUAL", effective_price_per_gram: null, price_source: "MANUAL", price_as_of: null, id: "coin", name: "Synthetic coin", form: "COIN", owner_name: "Demo owner", purity: "24K / 999", purchased_on: "2026-10-01", grams: "10.000000", total_cost: "60000.00", sold_grams: "0.000000", remaining_grams: "10.000000", remaining_cost: "60000.00", current_price_per_gram: null, price_updated_at: null, estimated_value: null, unrealized_profit: null, seller: "Demo shop", notes: "", removed: false }],
  sales: [], summary: { purchase_count: 1, grams_held: "10.000000", cost_of_holdings: "60000.00", total_paid: "60000.00", net_sale_receipts: "0.00", realized_profit: "0.00", estimated_value: null, unrealized_profit: null, priced_value: "0", unpriced_holdings: 1 },
};

test("Gold exposes a dedicated tab, missing-price state and read-only viewer holdings", () => {
  assert.ok(navigation.some((item) => item.href === "/gold" && item.label === "Gold"));
  const html = renderToStaticMarkup(createElement(GoldScreen, { workspaceId: "demo", canEdit: false, initialReport: report }));
  assert.match(html, /Synthetic coin/);
  assert.match(html, /1 holding needs a current price/);
  assert.match(html, /Add price/);
  assert.match(html, /role="tab" aria-selected="true"[^>]*>Holdings/);
  assert.match(html, />Sales<span/);
  assert.doesNotMatch(html, />Edit<|>Sell<|>Remove<|Add purchase/);
  assert.match(html, /Live gold prices unavailable/);
  assert.match(html, /do not change your IPO bank balances/);
  const owner = renderToStaticMarkup(createElement(GoldScreen, { workspaceId: "demo", canEdit: true, initialReport: report }));
  assert.match(owner, /Add purchase/); assert.match(owner, />Edit</); assert.match(owner, />Sell</);
});

test("Unavailable gold data cannot be mistaken for a zero balance", () => {
  const html = renderToStaticMarkup(createElement(GoldScreen, { workspaceId: "demo", canEdit: true, initialReport: null }));
  assert.match(html, /could not be loaded/); assert.match(html, /Try again/);
  assert.doesNotMatch(html, /Gold held|₹0|Add purchase/);
});

test("Gold filters hide removed records unless requested, including matching seller and owner", () => {
  const items = [...report.purchases, { ...report.purchases[0], id: "removed", removed: true }];
  assert.deepEqual(filterGold(items, "  demo SHOP ", false).map((item) => item.id), ["coin"]);
  assert.equal(filterGold(items, "demo owner", true).length, 2);
  assert.equal(filterGold(items, "22K", true).length, 0);
});

test("Gold preserves fractional grams and formats date-only values without a day shift", () => {
  assert.equal(goldGrams("0.000001"), "0.000001");
  assert.equal(goldGrams("12.340000"), "12.34");
  assert.equal(goldGrams("10.000000"), "10");
  assert.equal(goldDate("2026-10-01"), "01 Oct 2026");
  assert.equal(goldDate("2026-10-31T20:00:00Z"), "01 Nov 2026");
  assert.equal(goldError({ grams: ["Too much gold."], detail: "Please correct." }), "grams: Too much gold. Please correct.");
});

test("Gold values retain every paisa for large holdings and distinguish missing quotes", () => {
  assert.equal(goldAmount("99999999999999.99"), "₹9,99,99,99,99,99,999.99");
  assert.equal(goldAmount("-12.05"), "-₹12.05");
  assert.equal(goldAmount("60000.00"), "₹60,000");
  assert.equal(goldAmount(null), "—");
});

test("Live gold prices show attribution, per-purity INR rates and update time", () => {
  const live: GoldReport = { ...report, market: { ...report.market, state: "LIVE", as_of: "2026-10-31T12:00:00Z", rates: { "999": "9990.00", "916": "9160.00", "750": "7500.00" } } };
  const html = renderToStaticMarkup(createElement(GoldScreen, { workspaceId: "demo", canEdit: false, initialReport: live }));
  assert.match(html, /Live gold prices</); assert.match(html, /₹9,990/); assert.match(html, /₹9,160/); assert.match(html, /₹7,500/);
  assert.match(html, /Gold API/); assert.match(html, /Refresh prices/); assert.match(html, /17:30 IST/);
  const stale = renderToStaticMarkup(createElement(GoldScreen, { workspaceId: "demo", canEdit: true, initialReport: { ...live, market: { ...live.market, state: "STALE" } } }));
  assert.match(stale, /Last available gold prices/); assert.match(stale, /Using an older quote/);
  assert.equal(goldPriceLabel("UNKNOWN_PURITY"), "Set purity");
  assert.equal(goldPriceLabel("STALE"), "Last quote");
  assert.match(goldTimestamp("2026-10-31T20:00:00Z"), /01 Nov 2026, 01:30 IST/);
});

test("A failed refresh clears automatic estimates while preserving manual quotes and recorded money", () => {
  const automatic = { ...report.purchases[0], id: "auto", price_mode: "LIVE" as const, price_source: "LIVE" as const, effective_price_per_gram: "9990.00", estimated_value: "99900.00", unrealized_profit: "39900.00" };
  const manual = { ...report.purchases[0], effective_price_per_gram: "7000.00", estimated_value: "70000.00" };
  const failed = unavailableGoldReport({ ...report, purchases: [automatic, manual], summary: { ...report.summary, estimated_value: "169900.00", net_sale_receipts: "18500.00", realized_profit: "3500.00" } });
  assert.equal(failed.market.state, "UNAVAILABLE");
  assert.equal(failed.purchases[0].estimated_value, null); assert.equal(failed.purchases[0].price_source, "UNAVAILABLE");
  assert.equal(failed.purchases[1].estimated_value, "70000.00");
  assert.equal(failed.summary.estimated_value, null);
  assert.equal(failed.summary.priced_value, "70000.00");
  assert.equal(failed.summary.realized_profit, "3500.00");
  assert.equal(failed.summary.net_sale_receipts, "18500.00");
});
