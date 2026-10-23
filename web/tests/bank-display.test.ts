import assert from "node:assert/strict";
import { test } from "node:test";
import { bankIdentifiers } from "../src/lib/bank-display";

test("imported UPI references appear once while distinct account and UPI stay complete", () => {
  assert.equal(bankIdentifiers("synthetic@exampleupi", ["synthetic@exampleupi"]), "synthetic@exampleupi");
  assert.equal(bankIdentifiers("ACCOUNT0001", ["synthetic@exampleupi", "other@exampleupi"]), "ACCOUNT0001 · synthetic@exampleupi · other@exampleupi");
});
