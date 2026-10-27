import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PortfolioTabs } from "../src/app/portfolio/portfolio-screen";
import { portfolioTab, portfolioTabHref } from "../src/lib/portfolio-tabs";

test("Portfolio exposes three distinct tabs and retains dates when navigating", () => {
  const page = renderToStaticMarkup(createElement(PortfolioTabs, { activeTab: "results", fromDate: "2026-10-01", toDate: "2026-10-27" }));
  for (const label of ["Allotted holdings", "Realized results", "Recorded sales"]) assert.match(page, new RegExp(label));
  assert.match(page, /<a[^>]*aria-current="page"[^>]*>Realized results/);
  assert.equal((page.match(/aria-current=/g) ?? []).length, 1);
  assert.match(page, /tab=sales&amp;from_date=2026-10-01&amp;to_date=2026-10-27/);
  assert.equal(portfolioTabHref("results"), "/portfolio?tab=results");
  assert.equal(portfolioTab(), "holdings");
  assert.equal(portfolioTab(undefined, true), "results");
  assert.equal(portfolioTab("sales", true), "sales");
  assert.equal(portfolioTab("invalid"), "holdings");
});
