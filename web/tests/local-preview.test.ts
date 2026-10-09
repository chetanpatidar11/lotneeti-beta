import assert from "node:assert/strict";
import { test } from "node:test";
import { localPreviewEnabled } from "../src/lib/local-preview";

test("local preview needs an explicit flag and a development server", () => {
  assert.equal(localPreviewEnabled("development", "1"), true);
  assert.equal(localPreviewEnabled("development", undefined), false);
  assert.equal(localPreviewEnabled("production", "1"), false);
  assert.equal(localPreviewEnabled("test", "1"), false);
});
