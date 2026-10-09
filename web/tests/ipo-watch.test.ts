import assert from "node:assert/strict";
import { test } from "node:test";
import { missingPlanningFacts, watchPlanningMessage } from "../src/lib/ipo-watch";

test("exchange watch identifies the exact missing planning facts", () => {
  assert.equal(missingPlanningFacts(["lot_size", "allotment_date"]), "Planning unavailable · Missing: lot size, allotment date");
  assert.equal(missingPlanningFacts(["lower_price", "upper_price", "lot_size", "allotment_date"]), "Planning unavailable · Missing: lower price, upper price, lot size, allotment date");
  assert.equal(missingPlanningFacts([]), "Planning review pending");
});

test("exchange watch distinguishes discovery from completed source review", () => {
  assert.equal(watchPlanningMessage({ enrichment_state: "DISCOVERED", missing_planning_fields: ["lot_size", "allotment_date"] }), "Issue details not fetched yet");
  assert.equal(watchPlanningMessage({ enrichment_state: "ENRICHING", missing_planning_fields: ["allotment_date"] }), "Official document enrichment pending");
  assert.equal(watchPlanningMessage({ enrichment_state: "REVIEW_REQUIRED", missing_planning_fields: ["allotment_date"] }), "Planning unavailable · Missing: allotment date · Official source review required");
  assert.equal(watchPlanningMessage({ enrichment_state: "READY", missing_planning_fields: [] }), "Issue facts ready · Founder publication pending");
});
