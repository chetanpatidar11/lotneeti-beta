import assert from "node:assert/strict";
import test from "node:test";
import { validateBetaUrl } from "../scripts/validate-url-core.mjs";

test("accepts only a clean HTTPS beta origin", () => {
  assert.equal(validateBetaUrl("https://beta.example.invalid"), "https://beta.example.invalid");
  for (const value of ["", "http://beta.example.invalid", "https://user:pass@beta.example.invalid", "https://beta.example.invalid/sign-in", "https://beta.example.invalid/?token=secret", "https://beta.example.invalid/#section", "javascript:alert(1)"]) {
    assert.throws(() => validateBetaUrl(value));
  }
});
