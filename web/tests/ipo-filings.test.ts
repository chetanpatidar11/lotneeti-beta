import assert from "node:assert/strict";
import { test } from "node:test";
import { filingsForIssuer, type SEBIFiling } from "../src/lib/ipo-filings";

const filings: SEBIFiling[] = [
  { issuer_name: "Runwal Enterprises Limited", document_type: "RHP", document_url: "https://example.test/rhp", filing_date: "2026-09-24" },
  { issuer_name: "Runwal Enterprises Limited", document_type: "CORRIGENDUM", document_url: "https://example.test/corrigendum", filing_date: "2026-09-25" },
  { issuer_name: "Runwal Enterprises Holdings Limited", document_type: "DRHP", document_url: "https://example.test/other", filing_date: "2026-09-26" },
];

test("filing links match normalized exact issuer names and retain multiple documents", () => {
  assert.deepEqual(
    filingsForIssuer("Runwal Enterprises", filings).map((filing) => filing.document_type),
    ["RHP", "CORRIGENDUM"],
  );
});