import assert from "node:assert/strict";
import { test } from "node:test";
import { authPost } from "../src/lib/auth-post";
import { authRequestHeaders } from "../src/lib/auth-request";

const frontend = "http://127.0.0.1:3000";

function registrationRequest(extraHeaders: Record<string, string> = {}) {
  return new Request(`${frontend}/api/auth/register`, {
    method: "POST",
    headers: { ...authRequestHeaders, ...extraHeaders },
    body: JSON.stringify({ email: "person@example.test", password: "Safe test password 284!" }),
  });
}

test("a same-origin JSON request without Origin reaches registration", async (context) => {
  const calls: { url: string; origin: string | null }[] = [];
  context.mock.method(globalThis, "fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), origin: new Headers(init?.headers).get("origin") });
    return new Response(JSON.stringify({ message: "Check your email." }), { status: 200 });
  });

  const response = await authPost(registrationRequest({ "sec-fetch-site": "same-origin" }), "auth/register/");

  assert.equal(response.status, 200);
  assert.deepEqual(calls, [{
    url: "http://127.0.0.1:8000/api/v1/auth/register/",
    origin: frontend,
  }]);
});

test("a validation response is returned to the browser", async (context) => {
  context.mock.method(globalThis, "fetch", async () => new Response(
    JSON.stringify({ password: ["This password is too common."] }),
    { status: 400 },
  ));

  const response = await authPost(registrationRequest(), "auth/register/");

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { password: ["This password is too common."] });
});

test("cross-site and form requests are rejected before reaching Django", async (context) => {
  const requests = [
    registrationRequest({ origin: "https://other.example" }),
    registrationRequest({ "sec-fetch-site": "cross-site" }),
    new Request(`${frontend}/api/auth/register`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    }),
    new Request(`${frontend}/api/auth/register`, {
      method: "POST",
      headers: { ...authRequestHeaders, "content-type": "text/plain" },
      body: "{}",
    }),
  ];
  context.mock.method(globalThis, "fetch", async () => {
    throw new Error("A blocked request reached Django");
  });

  for (const request of requests) {
    const response = await authPost(request, "auth/register/");
    assert.equal(response.status, 403);
  }
});
