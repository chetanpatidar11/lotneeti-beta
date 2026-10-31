import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { navigation } from "../src/app/app-nav";
import CheckAllotmentScreen from "../src/app/check-allotment/check-allotment-screen";

test("Check Allotment has a separate navigation destination and page controls", () => {
  assert.deepEqual(navigation.filter((item) => item.label === "Check Allotment").map((item) => item.href), ["/check-allotment"]);
  const page = renderToStaticMarkup(createElement(CheckAllotmentScreen, { workspaceId: "synthetic", canEdit: true, initialItems: [] }));
  assert.match(page, /<h1>Check Allotment<\/h1>/);
  assert.match(page, /Allotment IPO selection/);
  assert.match(page, /Check this IPO/);
  assert.match(page, /Check all pending IPOs/);
  assert.match(page, /href="\/applications"/);
});

test("read-only members can open the checker without starting checks; load failure stops actions", () => {
  const props = { workspaceId: "synthetic", canEdit: false, initialItems: [] };
  const page = renderToStaticMarkup(createElement(CheckAllotmentScreen, props));
  assert.match(page, /Check Allotment/);
  assert.doesNotMatch(page, /Check this IPO|Check all pending IPOs/);
  const failed = renderToStaticMarkup(createElement(CheckAllotmentScreen, { ...props, initialLoadError: true }));
  assert.match(failed, /Applications could not be loaded/);
  assert.doesNotMatch(failed, /IPO allotment checker/);
});
