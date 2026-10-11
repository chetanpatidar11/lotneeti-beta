import assert from "node:assert/strict";
import { test } from "node:test";
import { applySettingsAction, toggleSelected } from "../src/lib/settings-removal";

const starting = {
  investors: [{ id: "one", active: true }, { id: "two", active: true }],
  banks: [{ id: "bank-one", owner: "one", active: true }, { id: "bank-two", owner: "two", active: true }],
  linkedAccounts: {
    one: {
      demats: [{ id: "demat-one", active: true }],
      upis: [{ id: "upi-one", holder: "one", bank_id: "bank-one", active: true }],
    },
    two: {
      demats: [{ id: "demat-two", active: true }],
      upis: [{ id: "upi-two", holder: "two", bank_id: "bank-two", active: true }],
    },
  },
};

test("multi-select toggles an item only once", () => {
  assert.deepEqual(toggleSelected(["one"], "one", true), ["one"]);
  assert.deepEqual(toggleSelected(["one"], "two", true), ["one", "two"]);
  assert.deepEqual(toggleSelected(["one", "two"], "one", false), ["two"]);
});

test("removing selected investors hides their linked accounts and preserves other investors", () => {
  const removed = applySettingsAction(starting, "investor", ["one"], "remove");
  assert.equal(removed.investors[0].active, false);
  assert.equal(removed.banks[0].active, false);
  assert.equal(removed.linkedAccounts.one.demats[0].active, false);
  assert.equal(removed.linkedAccounts.one.upis[0].active, false);
  assert.equal(removed.investors[1].active, true);
  assert.equal(removed.banks[1].active, true);
  assert.equal(removed.linkedAccounts.two.upis[0].active, true);

  const restored = applySettingsAction(removed, "investor", ["one"], "restore");
  assert.equal(restored.investors[0].active, true);
  assert.equal(restored.banks[0].active, false);
  assert.equal(restored.linkedAccounts.one.demats[0].active, false);
});

test("removing a bank hides its UPI and restoring the bank leaves UPI selection explicit", () => {
  const removed = applySettingsAction(starting, "bank", ["bank-one"], "remove");
  assert.equal(removed.banks[0].active, false);
  assert.equal(removed.linkedAccounts.one.upis[0].active, false);
  assert.equal(removed.investors[0].active, true);
  const restored = applySettingsAction(removed, "bank", ["bank-one"], "restore");
  assert.equal(restored.banks[0].active, true);
  assert.equal(restored.linkedAccounts.one.upis[0].active, false);
});

test("permanent deletion removes selected records and linked accounts from Settings", () => {
  const deleted = applySettingsAction(starting, "investor", ["one"], "delete");
  assert.deepEqual(deleted.investors.map((item) => item.id), ["two"]);
  assert.deepEqual(deleted.banks.map((item) => item.id), ["bank-two"]);
  assert.equal(deleted.linkedAccounts.one, undefined);
  assert.equal(deleted.linkedAccounts.two.upis.length, 1);
  const deletedBank = applySettingsAction(starting, "bank", ["bank-one"], "delete");
  assert.deepEqual(deletedBank.banks.map((item) => item.id), ["bank-two"]);
  assert.equal(deletedBank.linkedAccounts.one.upis.length, 0);
});
