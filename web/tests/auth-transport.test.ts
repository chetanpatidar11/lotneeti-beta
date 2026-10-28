import assert from "node:assert/strict";
import { test } from "node:test";
import { authTransport } from "../src/lib/auth-transport";

test("production auth keeps distinct trusted visitors on the private transport", () => {
  const first = authTransport("auth/password/login/", "198.51.100.1", true, "https://beta.example.test");
  const second = authTransport("auth/password/login/", "2001:db8::2", true, "https://beta.example.test");
  assert.equal(first.url, "http://127.0.0.1:8000/api/v1/auth/password/login/");
  assert.equal(first.headers.host, "beta.example.test");
  assert.equal(first.headers["x-forwarded-proto"], "https");
  assert.equal(first.headers.origin, "https://beta.example.test");
  assert.equal(first.headers["x-real-ip"], "198.51.100.1");
  assert.equal(second.headers["x-real-ip"], "2001:db8::2");
});

test("production auth rejects absent, malformed and appended visitor addresses", () => {
  for (const ip of [null, "", "unknown", "198.51.100.1, 198.51.100.2"]) {
    assert.throws(() => authTransport("auth/register/", ip, true, "https://beta.example.test"));
  }
});
