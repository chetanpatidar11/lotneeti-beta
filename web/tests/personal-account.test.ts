import assert from "node:assert/strict";
import test from "node:test";
import { selectedWorkspace } from "../src/lib/workspace";

test("account pages consistently use the first personal scope without a workspace cookie", async () => {
  const scopes = [{ id: "personal" }, { id: "legacy" }];
  assert.equal(await selectedWorkspace(scopes), scopes[0]);
  assert.equal(await selectedWorkspace([]), undefined);
});
