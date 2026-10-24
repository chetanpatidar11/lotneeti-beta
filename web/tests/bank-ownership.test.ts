import assert from "node:assert/strict";
import { test } from "node:test";
import { reassignBankUpis } from "../src/lib/bank-ownership";

test("editing a regular bank moves active and inactive UPIs immediately without touching other accounts", () => {
  const accounts = {
    one: { demats: [{ id: "demat-one" }], upis: [
      { id: "upi-a", holder: "one", bank_id: "bank-a", active: true },
      { id: "upi-b", holder: "one", bank_id: "bank-a", active: false },
      { id: "upi-c", holder: "one", bank_id: "bank-b", active: true },
    ] },
    two: { demats: [{ id: "demat-two" }], upis: [{ id: "upi-d", holder: "two", bank_id: "bank-c", active: true }] },
  };
  const changed = reassignBankUpis(accounts, "bank-a", "two");
  assert.deepEqual(changed.one.upis.map((upi) => upi.id), ["upi-c"]);
  assert.deepEqual(changed.two.upis.map((upi) => upi.id), ["upi-d", "upi-a", "upi-b"]);
  assert.ok(changed.two.upis.every((upi) => upi.holder === "two"));
  assert.equal(changed.two.upis.find((upi) => upi.id === "upi-b")?.active, false);
  assert.deepEqual(changed.one.demats, accounts.one.demats);
  assert.deepEqual(changed.two.demats, accounts.two.demats);
  assert.equal(accounts.one.upis.length, 3);
  assert.deepEqual(reassignBankUpis(changed, "bank-a", "two"), changed);
});

test("moving a bank to an investor without existing linked accounts retains UPI metadata", () => {
  const accounts = { one: { demats: [], upis: [{ id: "upi-a", holder: "one", bank_id: "bank-a", handle: "synthetic@exampleupi" }] } };
  const changed = reassignBankUpis(accounts, "bank-a", "new-holder");
  assert.deepEqual(changed["new-holder"], { demats: [], upis: [{ id: "upi-a", holder: "new-holder", bank_id: "bank-a", handle: "synthetic@exampleupi" }] });
});
