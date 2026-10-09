# Open gates and founder supplied inputs

This file is a fill-in worksheet for gates that cannot be completed with local synthetic data. Do not put real PANs, bank numbers, UPI handles, passwords, tokens or cloud keys in this repository. Keep completed worksheets outside Git, or copy only sanitized decisions and results into the handoff.

## B07/B08 account import

The supplied `docs/samples/AccountImportTemplate.xlsx` is a column-format example, not a ready-to-import data file: its CDSL and NSDL rows repeat the same PAN to illustrate the different demat fields. The workbook must have exactly one sheet and use this exact header order; the sheet tab name may vary:

`Name, PAN, Type, DPID, CLIENT ID, UPI ID, Account Number, Bank Name`

`Type` is `CDSL` or `NSDL`. `DPID` is required for NSDL. A CDSL row may leave DPID blank when CLIENT ID contains the complete BO identifier, as in the supplied sample. Valid rows are imported automatically after upload; rows with errors are skipped and remain visible in the preview. Imported banks start at Balance 0 and must be set by the user after import. Imported UPIs remain unverified until the user verifies them.

Each PAN may occur only once in an import workbook and may not already belong to an investor in the workspace. Both repeated-PAN sample rows show row errors and are skipped as supplied. Make a local copy with unique synthetic PANs, account numbers and UPI IDs to test successful multi-row import; keep the same eight columns.

Local acceptance:

```bash
cd /Users/chetanpatidar/Projects/lotneeti-new
.venv/bin/python -m pytest backend/tests/test_account_imports.py
bash scripts/check.sh
```

Manual acceptance in the running web app:

1. Sign in to a synthetic workspace and open Settings.
2. Choose `docs/samples/AccountImportTemplate.xlsx` under Import accounts. Verify both sample rows show a duplicate-PAN error and neither is imported.
3. Make a local copy with unique synthetic PAN, bank account and UPI values in the existing columns; upload it and verify valid rows import automatically and PAN, demat, UPI and account values are masked in the result.
4. Upload a copy containing one valid and one invalid row. Verify the valid row imports automatically and the invalid row remains visible with its error.
5. Reupload the same unique-PAN copy; verify the already-imported PAN shows an error and is not imported again.
6. Set the imported bank Balance and verify the imported UPI is still unverified until manually verified.

## G03 broker workbook mapping

The application has a deterministic generic CSV export. As of 2026-09-27, `docs/samples/` contains one `.xlsx` file, `AccountImportTemplate.xlsx`, for B07/B08. `BrokerExportMapping.template.csv` contains column headings and a blank row only. It does not define any broker destination columns. The broker workbook adapter remains blocked until the broker's approved workbook and mapping are supplied. Fill the mapping outside Git using `docs/samples/BrokerExportMapping.template.csv` and provide:

- the exact workbook file and sheet name;
- destination column names and order;
- required/optional status for every destination column;
- formatting rules for dates, amounts, category and lots;
- whether identifiers must be plaintext, masked or separately approved;
- one sanitized expected output for a two-row synthetic plan.

Acceptance commands after the mapping is approved:

```bash
.venv/bin/python -m pytest backend/tests/test_export_adapters.py backend/tests/test_saved_plan_csv_export.py
bash scripts/check.sh
```

Then add the approved template and adapter tests, run the full gate, and manually compare row order, identifiers, category, lots, amount and total against the broker's acceptance file. Do not connect a real broker account.

## K02 GMP freshness and conflict decision — resolved locally

On 2026-09-28 the Founder approved editable beta defaults of 24 hours for GMP freshness and 5.00 GMP percentage points relative to the effective IPO upper price for source conflict. The local implementation excludes stale observations from consensus, takes the median of the latest fresh enabled observation per source, marks disagreement at the threshold, preserves every source value, and gives an active Founder correction precedence. Founder Admin can edit both settings with a reason and audit trail. See [`docs/DATA_PROVIDERS.md`](../DATA_PROVIDERS.md) for exact boundaries and the exception view.

Separate external inputs remain open: approved NSE/BSE/SEBI feed access/schema/redistribution terms and an IPO field merge policy before promoting exchange snapshots into canonical IPO facts. These are feed integration gates, not missing K02 GMP defaults.

## M03 historical golden plans

Use `docs/samples/historical-golden-plan.template.json` once the founder has sanitized each case. Keep PAN aliases such as `PAN-01`, never real PANs. For each case, record the exact snapshot time, selected IPOs, current balances, blocks, debits, limits, preferences, locks, expected mappings, uncovered rows and the reason each expected result is correct.

Manual review:

1. Supply 15–25 sanitized cases covering ordinary, scarce cash, overlapping IPOs, EMI timing, cross-funding, sHNI upgrades, locks and allotment reuse.
2. Review each expected mapping with the founder.
3. Mark intentional differences from Planner v2 with a reason and approval date.
4. Convert approved cases to immutable test fixtures and run `bash scripts/check.sh`.

## Platform policy configuration

The founder-approved beta policy is `WARN`. Set the uppercase value explicitly in each environment before starting Django:

```bash
export PLANNER_PLATFORM_CROSS_FUNDING_POLICY=WARN   # ALLOW and DISALLOW are also supported
```

The local `.env` uses this value. Planner preview returns 503 when the setting is absent or not one of the uppercase policy values.

## AWS and backup gates

These steps require AWS credentials, a domain/TLS certificate, a chargeable EC2 host and private S3 buckets. Perform them only when the founder authorizes that spend. The exact runbooks are [`deploy/EC2_BETA.md`](../../deploy/EC2_BETA.md) and [`deploy/BACKUPS.md`](../../deploy/BACKUPS.md). The command sequence is recorded in `docs/FINAL_HANDOFF.md`.

## Android gate

The local package is a hosted-site launcher. A Java/Android SDK installation, reachable HTTPS host, APK build, signing decision and physical-device test are required. Use `mobile/README.md` and the command sequence in `docs/FINAL_HANDOFF.md`.
