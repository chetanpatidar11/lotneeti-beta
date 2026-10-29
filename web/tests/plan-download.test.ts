import assert from "node:assert/strict";
import test from "node:test";
import { downloadPlanCsv } from "../src/lib/plan-download";

test("export errors show backend guidance and reject invalid files before downloading", async () => {
  await assert.rejects(downloadPlanCsv(new Response(JSON.stringify({ detail: "Resolve blocking plan issues before export" }), { status: 409 })), /Resolve blocking plan issues/);
  await assert.rejects(downloadPlanCsv(new Response("unavailable", { status: 503 })), /could not export/);
  await assert.rejects(downloadPlanCsv(new Response('{}', { headers: { "content-type": "application/json" } })), /did not return a CSV/);
  await assert.rejects(downloadPlanCsv(new Response('', { headers: { "content-type": "text/csv" } })), /empty/);
});

test("successful CSV downloads use the returned file and filename then release the blob", async (context) => {
  const steps: string[] = [];
  const link = { href: "", download: "", click() { steps.push("click"); }, remove() { steps.push("remove"); } };
  const previous = Object.getOwnPropertyDescriptor(globalThis, "document");
  Object.defineProperty(globalThis, "document", { configurable: true, value: {
    createElement: () => link, body: { appendChild: () => steps.push("append") },
  } });
  context.mock.method(URL, "createObjectURL", (blob: Blob) => { assert.equal(blob.size, 7); return "blob:synthetic"; });
  context.mock.method(URL, "revokeObjectURL", (url: string) => { assert.equal(url, "blob:synthetic"); steps.push("release"); });
  context.mock.method(globalThis, "setTimeout", ((callback: () => void) => { callback(); return 0; }) as unknown as typeof setTimeout);
  try {
    await downloadPlanCsv(new Response("a,b\n1,2", { headers: { "content-type": "text/csv", "content-disposition": 'attachment; filename="demat-demo.csv"' } }));
    assert.equal(link.href, "blob:synthetic");
    assert.equal(link.download, "demat-demo.csv");
    assert.deepEqual(steps, ["append", "click", "remove", "release"]);
  } finally {
    if (previous) Object.defineProperty(globalThis, "document", previous);
    else Reflect.deleteProperty(globalThis, "document");
  }
});
