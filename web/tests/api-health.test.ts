import assert from "node:assert/strict";
import { test } from "node:test";
import { getApiHealth } from "../src/lib/api-health";

test("calls the versioned health endpoint and accepts its response", async () => {
  const called: string[] = [];
  const health = await getApiHealth("http://localhost:8000/api/v1/", async (input) => {
    called.push(String(input));
    return new Response(JSON.stringify({ status: "ok", apiVersion: "v1" }), { status: 200 });
  });

  assert.deepEqual(called, ["http://localhost:8000/api/v1/health/"]);
  assert.deepEqual(health, { connected: true, message: "API connected" });
});

test("shows an unavailable state when the endpoint cannot be reached", async () => {
  const health = await getApiHealth("http://localhost:8000/api/v1", async () => {
    throw new Error("Connection refused");
  });

  assert.deepEqual(health, { connected: false, message: "API is unavailable" });
});
