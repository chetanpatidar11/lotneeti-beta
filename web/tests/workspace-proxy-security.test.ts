import assert from "node:assert/strict";
import { test } from "node:test";
import { NextRequest } from "next/server";
import { proxyWorkspaceRequest, proxyWorkspaceUpload } from "../src/lib/proxy";

const frontend = "http://127.0.0.1:3000";

function request(method: string, headers: Record<string, string> = {}) {
  return new NextRequest(`${frontend}/api/workspaces/example/banks`, {
    method,
    headers,
    ...(method === "GET" ? {} : { body: "{}" }),
  });
}

test("workspace mutations reject cross-site requests before forwarding credentials", async (context) => {
  context.mock.method(globalThis, "fetch", async () => {
    throw new Error("A blocked request reached Django");
  });
  const untrusted = [
    request("POST", { origin: "https://other.example" }),
    request("PATCH", { "sec-fetch-site": "cross-site" }),
    request("DELETE"),
  ];
  for (const item of untrusted) {
    assert.equal((await proxyWorkspaceRequest(item, "workspaces/", item.method as "POST" | "PATCH" | "DELETE")).status, 403);
  }
  assert.equal((await proxyWorkspaceUpload(request("POST", { origin: "https://other.example" }), "workspaces/")).status, 403);
});

test("same-origin workspace mutations and reads reach Django", async (context) => {
  const methods: string[] = [];
  context.mock.method(globalThis, "fetch", async (_input: RequestInfo | URL, init?: RequestInit) => {
    methods.push(init?.method ?? "GET");
    return new Response("{}", { status: 200 });
  });
  const posted = await proxyWorkspaceRequest(request("POST", { origin: frontend, "content-type": "application/json" }), "workspaces/", "POST");
  assert.equal(posted.status, 200);
  assert.equal(posted.headers.get("cache-control"), "private, no-store");
  assert.equal((await proxyWorkspaceRequest(request("DELETE", { "sec-fetch-site": "same-origin" }), "workspaces/", "DELETE")).status, 200);
  assert.equal((await proxyWorkspaceRequest(request("GET"), "workspaces/", "GET")).status, 200);
  assert.deepEqual(methods, ["POST", "DELETE", "GET"]);
});

test("CSV proxy preserves UTF-8 file bytes and the attachment filename", async (context) => {
  const body = "Name,PAN\nSynthetic ₹,TESTX0001A\n";
  context.mock.method(globalThis, "fetch", async () => new Response(body, {
    headers: { "content-type": "text/csv; charset=utf-8", "content-disposition": 'attachment; filename="demat-synthetic.csv"' },
  }));
  const response = await proxyWorkspaceRequest(request("POST", { origin: frontend }), "workspaces/demo/planner/runs/demo/exports/", "POST");
  assert.equal(response.headers.get("content-type"), "text/csv; charset=utf-8");
  assert.equal(response.headers.get("content-disposition"), 'attachment; filename="demat-synthetic.csv"');
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  assert.equal(await response.text(), body);
});
