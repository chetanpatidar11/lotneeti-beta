import assert from "node:assert/strict";
import { test } from "node:test";
import { movePriority, sortByPriority } from "../src/lib/priorities";

test("lower priority is first and equal values use stable ID", () => {
  const investors = [
    { id: "b", planning_priority: 2 },
    { id: "c", planning_priority: 1 },
    { id: "a", planning_priority: 1 },
  ];
  assert.deepEqual(sortByPriority(investors).map((item) => item.id), ["a", "c", "b"]);
});

test("moving a row updates the visible numeric order", () => {
  const investors = [
    { id: "a", planning_priority: 1 },
    { id: "b", planning_priority: 2 },
    { id: "c", planning_priority: 3 },
  ];
  assert.deepEqual(movePriority(investors, 2, -1), [
    { id: "a", planning_priority: 1 },
    { id: "c", planning_priority: 2 },
    { id: "b", planning_priority: 3 },
  ]);
});
