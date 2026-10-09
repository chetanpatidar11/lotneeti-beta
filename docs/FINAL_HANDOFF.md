# LotNeeti founder beta handoff — draft, not release approval

**Current local completion pass, 2026-09-29 — not deployed.** Open the local preview at `http://127.0.0.1:3000/` (Django `127.0.0.1:8000`, Next `127.0.0.1:3000`, isolated SQLite `/private/tmp/lotneeti-local-preview.sqlite3`). The newest NSE list, Issue Information details and official RHP/SEBI timetable extraction yield **11 READY current IPOs**: eight NSE Mainboard and three NSE EMERGE. All 11 were published only in the isolated preview; a second run was idempotent. GREENASIA, BMISL and HIMALAYAN are NSE EMERGE with BSE `NOT_APPLICABLE`, based on their official RHP covers. AONESTEELS is dual listed with BSE designated. MONEYVIEW lot 441 and AONESTEELS lot 37 came from NSE detail. BSE automatic discovery remains unavailable under the current permitted method (zero current BSE Mainboard/SME records), so cross-exchange verification has **not** been claimed. The Founder confirmed written permission for a one-daily InvestorGain GMP retrieval. The **09:00 IST** local run saved nine GMP values (A-One ₹28, AceVector ₹2, Bench Mark ₹29, German Green Steel ₹24.50, Moneyview ₹12.75, Orient ₹72, Runwal ₹14, Shah ₹14 and SRIT ₹33); GREENASIA and HIMALAYAN have no source GMP and remain unavailable rather than ₹0. The agreement remains private, outside Git. K02 median/freshness/conflict defaults are unchanged.

The code schedules one coordinated IPO sync at **00:00 Asia/Kolkata** and the permissioned GMP check at **09:00 Asia/Kolkata**, with no provider-health polling job. The NSE job requires `LOTNEETI_NSE_SOURCE_RIGHTS_REFERENCE` and `LOTNEETI_IPO_SOURCE_CACHE_DIR` in the private process environment. BSE reports a source-access blocker independently, SEBI continues, and GMP exits without a request when no relevant IPO is published. Founder Admin and `manage.py sync_ipo_data` use the same coordinator. **`bash scripts/check.sh` passed after this update: 347 backend, 27 frontend, one Android test; Planner matrix 115/115 P0 and 5/5 P1; lint, typecheck, migrations and builds.** G03 still needs the approved broker workbook/mapping and M03 still needs founder-approved historical plans. The previous 8/3 and zero-plannable local notes below are retained only as historical state; the older AWS staging build is separate and was not accessed or changed in this pass.

An isolated copy of the local preview database passed a real-market/synthetic-account workflow using SRIT's official 115-share lot and ₹130 upper band: Add Money, Apply/Skip, two-row plan, locked re-plan, validation, save, generic CSV export, Submitted, Blocked, allotment releasing ₹14,950, sale and ₹105 realized profit. The review database was unchanged by this drill. Authenticated HTTP returned 200 for all seven primary routes and `/ipos` rendered the 11 saved current issues in HTML. **Rendered visual review remains a blocker:** macOS Chrome/Chromium exited before a screenshot, computer-use approval denied Chrome, the in-app browser was unavailable, and an isolated WebKit install stalled. The 1440/1280/1024/768/390px screenshot, overflow and Founder Admin MFA visual gates have not passed. CSS was adjusted for 44px mobile controls and the two-column IPO date fact, but this is not a substitute for browser inspection. Android package tests and Capacitor sync passed; APK/device acceptance remains open.

To repeat local publication after approved local enrichment: `LOTNEETI_TEST_DB=/private/tmp/lotneeti-local-preview.sqlite3 .venv/bin/python backend/manage.py publish_ready_ipos --rights-reference founder-attested-written-permission-2026-09-28-local-beta --settings=config.settings.test`. Inspect exact facts and provenance with `LOTNEETI_TEST_DB=/private/tmp/lotneeti-local-preview.sqlite3 .venv/bin/python backend/manage.py show_live_ipos --settings=config.settings.test`. Keep raw source files and rights documents outside Git. This is a founder preview, not production or release approval.

### Earlier local and deployed records (historical)

**Latest local D03 update, 2026-09-28 — not deployed.** The local NSE pipeline now treats the issue list as discovery, enriches all 11 current active/forthcoming symbols from NSE Issue Information detail, extracts explicit timetable dates from linked official NSE RHPs and matched SEBI RHPs, and validates completeness after enrichment. Current detail supplied Moneyview Bid Lot **441** and A-One Steels Bid Lot **37**. Eight EQ issues are published/READY in the isolated local SQLite preview (AONESTEELS, MONEYVIEW, ACEVECTOR, GERMAN, ORIENTCABL, RUNWALENTR, SHAHINVEST, SRIT). GREENASIA, BMISL and HIMALAYAN have complete NSE facts but remain REVIEW_REQUIRED/unpublished because BSE detail is inaccessible and cannot be cross-verified. GMP still needs a permitted source. The complete lot/date/source list and exact limits are in [`docs/LIVE_DATA_AUDIT.md`](LIVE_DATA_AUDIT.md); `show_live_ipos` prints each attempted source and field provenance. The older list-only and zero-plannable statements below describe the earlier local/AWS state and are superseded for this local preview.

**Review locally:** `http://127.0.0.1:3002/ipos` is the fresh local preview (Django `:8002`, Next `:3002`); authenticated `/ipos` and `/plan` returned HTTP 200, with eight real IPO cards and three BSE review rows. Earlier `:3001/:8001` processes may serve old code. The source label now uses `Source: NSE · Fetched: …` and shows a source update only if NSE provides one. `bash scripts/check.sh` passed **335 backend, 27 frontend and one Android test**, all 115 P0/five P1 Planner matrix mappings, Ruff, Django/migration, web lint/typecheck/build and Capacitor gates. Browser screenshot/viewport inspection and Founder acceptance remain open. No AWS access, deployment or service restart occurred; the AWS beta still has the earlier list-only build.

To repeat the local data pass in test SQLite, run `LOTNEETI_TEST_DB=/private/tmp/lotneeti-local-preview.sqlite3 .venv/bin/python backend/manage.py enrich_live_ipos --saved-dir /private/tmp --fetch --refresh-discovery --settings=config.settings.test`, then the same prefix with `show_live_ipos --settings=config.settings.test`. To publish READY records **in test SQLite only**, use `publish_ready_ipos --rights-reference founder-attested-written-permission-2026-09-28-local-beta --settings=config.settings.test` with the same database prefix. Keep fetched originals outside Git. BSE automatic access remains disabled; a saved permissioned BSE detail can be imported via `import_bse_ipo_detail`. Current SEBI matching searches official issuer results beyond the recent index; exhaustive pagination remains open. This is a beta preview, not release approval.

Local Settings update, 2026-09-28 (**not deployed**): Investors and Accounts now support per-row Delete, multi-select Delete selected, Show deleted and Restore. Deletion archives the record from active planning and retains financial/application history; investor and bank removal archives linked accounts. Removal is blocked until selected bank balances are zero, active scheduled payments are paused/deleted, and open applications have results. Child accounts must be restored separately after their investor or bank. Workspace permissions, all-or-nothing bulk validation and audit events are enforced in the new Settings items API. `bash scripts/check.sh` passed **323 backend, 25 frontend and one Android test**, plus Planner/lint/type/build/migration gates. Local web-proxy bulk delete and restore of two synthetic investors passed. Open `http://127.0.0.1:3001/settings/investors` for local review; it uses the opt-in synthetic loopback sign-in and three synthetic test investors. Browser screenshot access was denied, so visual review remains open. **The AWS staging URL below still serves the earlier build without these Delete controls**, per the Founder’s no-deploy instruction.

Earlier staging refresh, 2026-09-28: **the then-current build was deployed for founder testing at `https://44-192-105-250.sslip.io/`** on the existing low-cost EC2 beta. The Founder explicitly authorized this staging refresh after the formal release-readiness review below. No new infrastructure, domain, SES identity or paid data provider was added. The deployed archive SHA-256 is `f87140f77505cb8ac76ee304350cb606a497e714731055982961ccd86829f065`; the release contains uncommitted local D03/K02/SEBI/frontend worktree changes. A `git add` attempt failed because this sandbox cannot create `.git/index.lock`, so use the archive hash to identify the live source until it can be committed. `bash scripts/check.sh` passed beforehand: 319 backend tests, 22 frontend tests, one Android package test and the Planner/lint/type/build/migration gates. On EC2, Next.js built, Django production check passed, and migrations through `ipos.0015` applied. API, web, worker, beat, Nginx, PostgreSQL, Redis and the backup timer are active.

Live smoke checks: valid-TLS HTTPS 200 for health, home, sign-in and IPO routes; HTTP 301 to HTTPS; health JSON and HSTS/nosniff/frame/referrer/opener headers correct. Founder Admin redirected to login; unauthenticated IPO feed-watch returned 403; local-preview authentication returned 404 in production. The founder-approved cross-funding policy remains `WARN`, and SES delivery remains enabled. A fresh sign-in email request for the already verified founder inbox returned 200; the Founder should open the new email link to complete this deployment's inbox/use check (look in Spam if needed). Staging now has 25 saved official SEBI filing links and 11 offline-imported NSE watch observations. It has **no published/plannable canonical IPO and no automatic GMP**; the watch and filing links cannot enter plans.

Backup verification: a private encrypted pre-deployment backup was retained as `backups/postgres/releases/2026-09-28-before-staging-refresh.dump.gcm` (143286 bytes, S3 AES256). A post-deployment encrypted daily backup (165283 bytes, S3 AES256) restored successfully into an isolated PostgreSQL database. All 47 table row counts matched live, including 58 migrations, one workspace, 25 SEBI filings, 11 NSE observations and zero saved plan runs/applications/sales; the isolated database was removed afterward. The nightly backup timer remains active. Existing AWS resources and estimated recurring services are listed in the deployment section below. G03, M03, live IPO/GMP rights/completeness, visual review and Android/device acceptance remain open; **this is a test beta, not production approval**. For later updates, run `bash scripts/check.sh` and the exact `deploy/push-from-workstation.sh` command already recorded below, then repeat smoke and backup/restore checks.

Founder workbook review, 2026-09-28: `docs/DematAccounts_testing.xlsx` contains 17 CDSL rows in the approved eight-column account-import order. It is kept out of Git because it contains account identifiers. Its sheet is named `Worksheet` rather than the required `AccountImportTemplate`; every row lacks Account Number and Bank Name, and one PAN fails format validation. No row is currently importable. No account data was imported locally or into AWS. A private corrected copy can be previewed under Settings after those fields and the sheet name are fixed. This workbook does not supply the G03 broker export layout or M03 approved historical plan cases, so the deployment readiness decision below is unchanged.

Formal release-readiness review before staging authorization, 2026-09-28: The approved backlog still has two open P0 founder-beta tickets: G03 needs the agreed broker export workbook and destination mapping, and M03 needs 15–25 sanitized founder-reviewed historical plans with approved expected mappings. The requested visual review at five viewport widths and Android/device acceptance are also open; Chrome computer-use access was denied again. The current NSE/SEBI watch has no complete published/plannable real IPO and no automatic GMP. `bash scripts/check.sh` passed **319 backend tests, 22 frontend tests, one Android test** and all configured planner/lint/type/build/migration gates; a fresh SQLite migration applied through `ipos.0015`. At this earlier review, the existing AWS beta HTTPS health endpoint returned 200 but served the previous deployed revision; no deploy occurred in that review. The subsequent Founder staging authorization and deployment are recorded above. This environment remains a founder test beta, not production approval.

Updated 2026-09-27. The local implementation and automated gate are green, and the single-host AWS beta is live at `https://44-192-105-250.sslip.io/`. SES email sign-in is verified with one founder inbox, and the founder-approved beta platform funding policy is `WARN`. Founder-supplied product inputs and Android/device acceptance remain gates. This is a founder test environment, not production approval. No OpenAI API or paid external API was used; no real PAN or bank data was loaded.

Local update 2026-09-28 (not deployed): commit `77ed927` added normalized NSE/BSE/SEBI fixture/permitted-feed IPO observations with explicit canonical IPO links and immutable snapshots. The later Founder source-preference decision is now implemented locally: active correction; NSE/BSE official field selection with visible dual-exchange conflicts; SEBI/RHP provenance; then cached valid facts. Canonical links remain review-only until a Founder enables them with a permission reference. K02 GMP defaults are implemented locally: 24-hour freshness, 5-point source conflict, fresh-source median and Founder correction precedence, with editable MFA-gated Founder Admin controls and exception view. See [`docs/DATA_PROVIDERS.md`](DATA_PROVIDERS.md). No AWS resources were accessed or changed in this run.

The latest local gate passed with **311 backend tests, 22 frontend tests and 1 Android package test**; Planner v2 matrix, Ruff, Django checks/migration drift, frontend lint/typecheck/build and Capacitor gates passed. Migrations through `ipos.0013_ipofeedbatch` are included. Founder Admin review routes are `/admin/ipo-exceptions/` and `/admin/gmp-policy/` after separate Founder MFA login. The AWS beta still runs the earlier deployed code.

A sixth focused K02 test was added and passed. The local SQLite preview applied `ipos.0011`–`ipos.0013`. It now holds one saved official NSE current-issue response containing 11 issues, eight mainboard and three SME. The raw response is outside Git; an initial approximate-time import and a later capture-time import left 22 immutable observations for 11 current source identities. A complete-response marker ensures that issues dropped by a later response leave the current watch without erasing history. All lack official lot size and allotment date, so they appear in a read-only “Exchange watch” section on `/ipos` and cannot enter plans. Three SME rows also lack price bands. BSE's public IPO page returned HTTP 403 here; there is no BSE-source import. No GMP was invented. A local authenticated HTTP check returned 200 for the watch API and rendered all 11 saved issues. Customer requests read the database and make no NSE/BSE calls. The Founder attested written permission in chat, but the instrument/scope was not supplied for independent review. The complete import boundary and refresh command are in [`docs/DATA_PROVIDERS.md`](DATA_PROVIDERS.md).

Local frontend continuation: Applications now has a dense operational table and detail/result drawers; Portfolio has holdings, profit metrics, grouped reports and a sale drawer; Settings has tabs, a compact investor priority table, masked linked-account details, funding and add-investor drawers, and a separate import utility. Shared loading and error states were added. Founder Admin now has a dark shell and grouped operational home; existing MFA permissions stay in place. Existing backend result/sale endpoints provide the financial amounts; Planner v2 rules and calculations did not change. Review `/`, `/ipos`, `/plan`, `/funds`, `/applications`, `/portfolio` and `/settings/investors` at `http://127.0.0.1:3000/`, and `/admin/` with a separate local Founder MFA account. Chrome and Safari computer-use requests were automatically rejected and the in-app browser was unavailable, so screenshot inspection at 1440, 1280, 1024, 768 and 390px remains unfinished. Source, build, tests and authenticated HTTP checks passed; the redesign is still awaiting visual and founder review. No deployment was made.

The existing `:3000`/`:8000` local processes predate the D03 watch import and could not be stopped from this session (`Operation not permitted` on the old processes). The latest code was verified through temporary local `:3001`/`:8001` processes, which were stopped afterward. To view the new watch in a browser, restart the normal local servers using the commands below with `LOTNEETI_TEST_DB=/private/tmp/lotneeti-local-preview.sqlite3` and open `/ipos`. Do not expect the still-running older processes to show the new watch until restarted.

## 1. Fully complete locally

- A01-A08 foundation, including platform/workspace feature-flag resolution.
- B01-B09 investor, demat, bank, UPI, priority and inactive-applicant behavior.
- B07/B08 account import using the supplied synthetic `docs/samples/AccountImportTemplate.xlsx`: exact sheet and eight-column contract, bounded workbook XML parsing, encrypted preview batch, masked row review, row errors, selected-row confirmation, workspace scoping and viewer read-only behavior. The supplied CDSL/NSDL rows illustrate the format but repeat a PAN; both are rejected until the data is made unique. Existing workspace PANs are rejected too.
- C01-C10 Balance, Scheduled Payments/EMI and funding preferences/policy resolution.
- D01-D14 manual IPO/GMP providers, selection, overrides, provider health and content governance.
- E01-E20 Planner v2 core, deterministic snapshots, locks, repair, explanations, audit and preview.
- F01-F09 plan review/editing/validation and plain-language blocking/warning presentation.
- G01/G02/G04/G05 versioned generic CSV export, readiness checks, private-storage adapter and export metadata.
- H01-H07 application tracking, blocks, actual-cost allotment, partial allotment and dated history.
- I01-I03 sales, realized P&L, split-sale cost allocation and reports.
- J01-J08 responsive shell, dashboard, IPO/planner UX, formatting and accessibility code baseline.
- K01/K03-K07 Founder Admin, overrides, GMP health/corrections, AI content review, policies and redacted support lookup.
- L01-L12 implementation assets and tests. L06-L08/L11/L12 live cloud checks and the real restore drill passed; a real founder SES sign-in passed, while manual acceptance remains open.
- M01/M02/M04/M05/M06 Planner matrix mapping, synthetic 17-applicant fixture, frozen snapshots, synthetic API flow and privacy-safe beta events.

## 2. Automated evidence

Run from the repository root:

```bash
bash scripts/check.sh
```

The SES deployment local gate passed before and after deployment with 277 backend tests, 20 frontend tests and 1 Android package test. It also passed all 115 Planner v2 P0 and 5 P1 matrix mappings, Ruff check/format, Django checks, migration drift, frontend lint/typecheck/production build and Capacitor typecheck/build/sync.

Fresh migration verification:

```bash
LOTNEETI_TEST_DB=/private/tmp/lotneeti-fresh.sqlite3 \
  .venv/bin/python backend/manage.py migrate --noinput --settings=config.settings.test
```

The synthetic API scenario covers IPO APPLY, plan preview/edit/lock, generic CSV export, submission/block, partial allotment, sale and realized profit. The AWS host applied all 51 PostgreSQL migrations, passed `manage.py check --deploy`, built Next.js, performed a real encrypted S3 backup and isolated restore, and passed HTTPS/API/frontend connectivity checks. Remote CI, APK compilation and physical-device acceptance remain unverified.

## 3. Exact local setup and application commands

Prerequisites: Python 3.12+, Node.js 22+ and Docker Compose.

```bash
cd /Users/chetanpatidar/Projects/lotneeti-new
cp .env.example .env
# Edit .env: set a random local DJANGO_SECRET_KEY; use WARN to match the beta policy.
python3 -m venv .venv
.venv/bin/python -m pip install -e 'backend[dev]'
npm ci --prefix web
npm ci --prefix mobile
docker compose up -d postgres redis
.venv/bin/python backend/manage.py migrate
```

Terminal 1, Django API:

```bash
cd /Users/chetanpatidar/Projects/lotneeti-new
LOTNEETI_LOCAL_PREVIEW_AUTH=1 PLANNER_PLATFORM_CROSS_FUNDING_POLICY=WARN \
  .venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```

Terminal 2, Next.js web app:

```bash
cd /Users/chetanpatidar/Projects/lotneeti-new
LOTNEETI_LOCAL_PREVIEW_AUTH=1 FRONTEND_BASE_URL=http://127.0.0.1:3000 \
  API_BASE_URL=http://127.0.0.1:8000/api/v1 \
  npm run dev --prefix web
```

Open `http://127.0.0.1:3000`. The opt-in local preview signs in a synthetic `local-preview@lotneeti.test` user and creates an empty Local Preview workspace. It accepts only loopback requests and is disabled in production settings. Leave `LOTNEETI_LOCAL_PREVIEW_AUTH` unset to use normal email links. Create a separate synthetic founder account with `createsuperuser`, then run:

```bash
.venv/bin/python backend/manage.py enroll_founder_totp founder@example.test
```

When Docker is unavailable, use the isolated SQLite test settings for a local UI preview: run `LOTNEETI_TEST_DB=/private/tmp/lotneeti-local-preview.sqlite3 .venv/bin/python backend/manage.py migrate --settings=config.settings.test`, then add `LOTNEETI_TEST_DB=/private/tmp/lotneeti-local-preview.sqlite3`, `--settings=config.settings.test` and `--insecure` to the Django command above. `--insecure` is only for this local preview so Django serves the Founder Admin stylesheet under `DEBUG=False`. This preview has no production data or Redis-backed jobs.

Use only synthetic PANs such as `TESTX0001A`, fake account numbers and `person@example.test` addresses. The account-import manual flow and sample contract are documented in [`docs/manual-acceptance/OPEN_GATES.md`](manual-acceptance/OPEN_GATES.md).

## 4. Remaining blocked work

- G03: `docs/samples/` contains the account import `.xlsx`, but no broker workbook. [`docs/samples/BrokerExportMapping.template.csv`](samples/BrokerExportMapping.template.csv) has only headings and a blank row, so it defines no destination columns. Generic CSV is complete. Supply the approved broker workbook and filled mapping, then implement and compare the exact adapter output as described in [`docs/manual-acceptance/OPEN_GATES.md`](manual-acceptance/OPEN_GATES.md).
- External IPO/GMP providers: the Founder approved the source-preference policy and attested written public API permission. The exact permission scope/reference should be retained with project records before broader distribution or enabling canonical links. The current NSE list lacks required lot/allotment facts, and BSE's public IPO page returned 403; obtain accessible official complete records before promoting an issue to the planner. K02 GMP policy is resolved locally, but no current GMP source observation was available in this import. None of this local work is deployed to AWS.
- M03: 15–25 founder-approved sanitized historical expected plans and mappings are missing. Use [`docs/samples/historical-golden-plan.template.json`](samples/historical-golden-plan.template.json); synthetic snapshots cannot substitute for founder approval.
- Email sign-in is limited to verified recipient addresses while SES remains in sandbox. The first real sign-in email landed in Gmail Spam; founder testing should check Spam. For additional testers, verify each email identity in SES or request SES production access after separate approval. No AWS console action is needed for this one-inbox beta test.
- Android: the HTTPS beta host is now reachable, but Java/Android SDK, APK compilation/signing and physical-device acceptance remain open. The current package is a hosted-site launcher, not a bundled offline client.
- Frontend visual review: the local UI is running and all main routes pass authenticated HTTP checks, but computer-use approval rejected Chrome and Safari and no in-app browser was available. Layout, overflow, focus and touch-target checks at the requested five widths remain a manual review gate. The Django Founder Admin dark shell and grouped home passed template/static checks but need the same visual pass. Settings account details are masked/read-only; account creation beyond the existing import and funding flows remains a UX follow-up.
- Git metadata was writable for the earlier 2026-09-28 D03 commit `77ed927`. The latest canonical merge, NSE watch import, K02/frontend work and documentation remain uncommitted because this session cannot create `.git/index.lock` (`Operation not permitted`). `git diff --check` passed, and the saved official response stays outside Git.

## 5. Exact manual acceptance steps

1. Open `https://44-192-105-250.sslip.io/` (or run the local setup above).
2. Sign in with the verified founder inbox; check Gmail Spam if necessary, then verify sign-out and single-use link behavior. Other recipients require SES verification while sandboxed.
3. Create two workspaces, add OWNER/OPERATOR/VIEWER members and verify cross-workspace reads/writes fail.
4. Upload the sample workbook from Settings and verify both repeated-PAN rows show errors. Make a local copy with unique synthetic PAN, bank and UPI values in the same columns; review masked values, leave one valid row unchecked, confirm, set imported bank Balance and verify the UPI remains unverified.
5. Create/edit a synthetic investor, demat, bank and UPI manually; verify masking and numeric priority order.
6. Exercise Add Money, Remove Money, Set Balance and Scheduled Payments/EMI. Verify Balance, Blocked, Planned and Available.
7. As Founder Admin, create/publish a manual IPO and GMP observation. Test threshold selection, manual APPLY, manual SKIP and Reset to automatic.
8. Choose each IPO mode, generate a plan, edit applicant/category/lots/demat/bank/UPI, lock a row, re-plan unlocked rows and inspect explanations/warnings.
9. Verify a blocking plan cannot export, then export a ready plan as generic CSV and check row order, identifiers, category, lots, amount and total.
10. Track Submitted and Blocked applications; record not allotted, full allotment and partial allotment; verify next-day cash reuse.
11. Record split sales and charges; verify realized profit, ROI and IPO/investor/workspace date filters.
12. Run browser keyboard/focus checks and a screen-reader pass; warnings must have icon, label and text.
13. Review the local K02 GMP conflict/staleness view, then complete the G03 and M03 supplied-input steps before calling the beta product complete.

## 6. Exact Android APK commands

Requires Node 22+, Java, Android Studio, Android SDK API 36 and a deployed HTTPS site.

```bash
cd /Users/chetanpatidar/Projects/lotneeti-new/mobile
npm ci
npm run test
npm run typecheck
VITE_LOTNEETI_WEB_URL=https://44-192-105-250.sslip.io npm run android:sync
cd android
./gradlew assembleDebug
```

The debug APK is `mobile/android/app/build/outputs/apk/debug/app-debug.apk`. Install for device testing with:

```bash
adb install -r mobile/android/app/build/outputs/apk/debug/app-debug.apk
```

For a release APK, create a private keystore outside Git, configure Gradle signing locally, run `./gradlew assembleRelease`, and keep the keystore/passwords outside the repository. On a device verify launch, sign-in, navigation, CSV download, session return, offline/reconnect behavior and the final HTTPS host. Do not build against `https://beta.example.invalid`.

## 7. Live AWS founder beta

### Public URL and budget

- URL: `https://44-192-105-250.sslip.io/` (temporary DNS tied to public IPv4 `44.192.105.250`). The certificate expires 2026-12-26; Certbot renewal dry run passed and a renewal hook reloads Nginx.
- AWS account `497502378741`, region `us-east-1`. The founder explicitly allowed the existing root CLI session for infrastructure setup in this student account. Application S3 access uses the one scoped EC2 role, with no AWS keys on the host. The already existing account-wide `lotneeti-staging-monthly` USD 80 monthly budget received an ACTUAL >25% (USD 20) email alert to `chetanpatidar1011@gmail.com` before chargeable resources were created; both notification and subscriber were read back from AWS.

### Exact AWS resources created

- CloudFormation `lotneeti-beta-storage`: private buckets `lotneeti-beta-497502378741-us-east-1-exports` and `lotneeti-beta-497502378741-us-east-1-backups`, each with a bucket policy blocking plaintext/insecure uploads, all four public-access blocks and AES256 default encryption. IAM role `lotneeti-beta-storage-BetaInstanceRole-r7SzKQexYkXg` and instance profile `lotneeti-beta-storage-BetaInstanceProfile-tNBzy9G3HeQU` have managed policies `lotneeti-beta-storage-ExportAccessPolicy-OeENXfXOqSPH` and `lotneeti-beta-storage-BackupAccessPolicy-mgORcvGPUeYl` for the `exports/` and `backups/postgres/` prefixes, plus `lotneeti-beta-storage-SESAccessPolicy-ZVrpXR18IsgZ` scoped to `ses:SendRawEmail` from one verified identity. The stack is `UPDATE_COMPLETE`; no second role was created.
- SES `us-east-1` verified **email address** identity `chetanpatidar1011@gmail.com` (`arn:aws:ses:us-east-1:497502378741:identity/chetanpatidar1011@gmail.com`) is tagged `Project=LotNeeti`, `Environment=Beta`. No domain identity was created. SES is still in sandbox (`ProductionAccessEnabled=false`, 200 recipient sends per 24 hours, 1 send/second at verification). The default Essentials pricing plan was changed to `NONE` (à la carte) and read back as the current plan to minimize cost.
- CloudFormation `lotneeti-beta-host-active`: VPC `vpc-077af0b2864e9141a`, public subnet `subnet-0a460d17795032ae9`, internet gateway `igw-053b4936f929b5c91`, route table `rtb-05b87d428b1ce8214`, subnet route association `rtbassoc-059ac31374b37579d`, security group `sg-0def099f971811fba`, EC2 `i-02def39354f6c2377` and encrypted 30 GB gp3 volume `vol-049debf49fe68a75b`. The `t4g.small` runs Ubuntu 24.04 arm64 with standard CPU credits. SSH is restricted to `94.207.192.250/32`; ports 80 and 443 are public. The failed initial stack `lotneeti-beta-host` was deleted and created no instance.
- Tagged imported EC2 SSH key pair `key-0511fab53cceabcc3` (`lotneeti-beta-20260927`). Its private key is outside Git at `/private/tmp/lotneeti-beta-keys/lotneeti-beta-20260927`; a separate encrypted recovery copy is SSM SecureString `/lotneeti/beta/operator-ssh-private-key`, version 1. Move the working key to durable private local storage before temporary files are cleaned.
- Standard SSM SecureStrings `/lotneeti/beta/backup-encryption-key` and `/lotneeti/beta/django-secret-key`, both version 1, hold separate encrypted recovery copies of the PostgreSQL backup and Django field-encryption keys. Decryption/recovery comparisons succeeded without printing their values. The EC2 role has no SSM read permission.
- All supported resources carry `Project=LotNeeti` and `Environment=Beta`. No RDS, ECS/Fargate, load balancer, NAT Gateway, managed Redis, domain purchase, OpenAI API or paid external API was created or used.

### Verification

- The host built Next.js, passed Django `check --deploy`, applied all 51 migrations (including `core.0003_featureflag` and `investors.0003_accountimportbatch`), and collected static assets. Django/Gunicorn, Next.js, Celery worker/beat, PostgreSQL, Redis and Nginx are active. PostgreSQL/Redis listen only on loopback.
- HTTPS certificate trust passed; HTTP redirects 301. `GET /api/v1/health/` returns HTTP 200 and `{"status":"ok","service":"lotneeti-api","apiVersion":"v1"}`. `/sign-in` returns HTTP 200. The homepage renders `API connected`, and the unauthenticated frontend workspace proxy returns 403 through Django. Nginx adds HSTS, nosniff, frame denial, Referrer-Policy and COOP to frontend and API responses. `certbot renew --dry-run --no-random-sleep-on-renew` passed.
- The EC2 role wrote and read a synthetic AES256 private export and generated a working five-minute signed download. An unsigned request returned HTTP 403. The test export was deleted. Negative role checks denied account-wide bucket listing, backup writes outside `backups/postgres/`, and SSM secret reads.
- `lotneeti-backup.service` uploaded real encrypted S3 archives: `backups/postgres/daily/2026-09-27.dump.gcm`, `weekly/2026-W39.dump.gcm`, and `monthly/2026-09.dump.gcm`. Each is 141338 bytes with S3 AES256 encryption. The daily archive was authenticated and restored into the isolated database `lotneeti_restore_20260927` using PostgreSQL server/client 17.11. Live and restore counts matched: 51 migrations, 0 workspaces, 0 plan runs, 0 applications and 0 sales. The isolated database was dropped after recording the drill. The backup timer is enabled/active for 02:00 Asia/Kolkata nightly (next run observed 2026-09-28 02:00 IST); retention is 7 daily, 4 weekly and 3 monthly objects.
- The SES code change passed 277 backend tests, 20 frontend tests, 1 Android package test, Planner matrix, lint, typecheck, migration drift and builds before and after deployment. The workstation redeploy script succeeded with archive SHA-256 `67ae8fce10ab53a79f2e7463c67214a813cd6598d64dadd27a60ad7c11a7b347`; production Django check passed and no new migrations were needed. The previous base deployment archive was `8d54fd49edc6252ddc21781fbf748fc0f9b9fdaf24fe72f4579ad036b7408a9c`.
- `/etc/lotneeti/app.env` remains root-owned mode 0600, outside Git. It now sets `EMAIL_DELIVERY=ses`, `AWS_SES_REGION=us-east-1`, `DEFAULT_FROM_EMAIL=chetanpatidar1011@gmail.com`, and founder-approved `PLANNER_PLATFORM_CROSS_FUNDING_POLICY=WARN`; SMTP placeholders were removed. The EC2 role supplies AWS credentials. API, worker and beat were restarted and healthy. The beta sign-in request returned 200, SES counted one sent email, and Gmail received the actual `Sign in to LotNeeti` message in **Spam**. Its delivered link redirected to the homepage, set a Secure/HttpOnly session cookie, and `GET /api/v1/me/` returned 200 for the founder inbox. Link replay redirected to `/sign-in?error=link`. Health remained 200 after deployment.

### Estimated recurring AWS usage

At 730 hours/month before credits, taxes, transfers and variable S3/KMS requests: `t4g.small` about USD 12.26 (AWS Pricing API returned USD 0.0168/hour), 30 GB gp3 about USD 2.40, and one public IPv4 about USD 3.65, or about USD 18.31/month plus small S3 usage. AWS currently offers a shared 750-hour/month `t4g.small` free trial through 2026-12-31; if this account has those hours available, instance-hour charges may be covered, leaving roughly USD 6.05/month plus S3/transfer/tax. SES à la carte adds USD 0.10 per 1,000 outbound recipient emails (about USD 0.10 for 1,000 beta sign-ins), with no fixed monthly SES plan charge; usage remains subject to AWS credits/tax. Standard SSM Parameter Store has no additional monthly parameter charge; KMS requests may apply. The account-wide USD 20 alert is a notification, not a hard spending limit.

### Exact process for later code updates

From the current workstation, keep the SSH private key and known-hosts file outside Git. Review the worktree and run the local gate first:

```bash
cd /Users/chetanpatidar/Projects/lotneeti-new
bash scripts/check.sh
LOTNEETI_KNOWN_HOSTS=/private/tmp/lotneeti-beta-known-hosts \
  bash deploy/push-from-workstation.sh \
  44.192.105.250 \
  /private/tmp/lotneeti-beta-keys/lotneeti-beta-20260927 \
  44-192-105-250.sslip.io
```

The tested script archives the current `backend/`, `web/` and `deploy/` worktree without secrets/build directories, syncs source to `/opt/lotneeti`, installs the reviewed Nginx/systemd/renewal assets, runs `nginx -t`, installs Python and Node dependencies, builds Next.js, runs Django production checks and migrations, collects static files, restarts the four app services and checks HTTPS health. Environment files stay under `/etc/lotneeti/` outside Git. Preserve a previous reviewed source checkout for rollback; the script does not reverse database migrations. If the instance public IP changes, the temporary DNS name, certificate, host environment URLs and SSH security-group CIDR must be updated before using this command.

### Remaining deployment blockers

- SES remains in sandbox: only the verified founder inbox can currently receive sign-in mail. No manual AWS console step is needed for this inbox. For additional testers, verify only their specific email identities in SES and have each owner click the verification email; production access would require a separate SES request. Gmail placed the first founder sign-in email in Spam, likely because SES sent from a Gmail address without an owned domain. Check Spam during founder testing; there is no domain purchase in this beta plan.
- G03 broker workbook/mapping, M03 approved historical plans, BSE access/complete official IPO fields, written permission scope, visual and Android/device manual acceptance remain as listed above. K02 and D03 rules are locally implemented but not deployed. No real PAN, bank or application data has been loaded. Do not call this environment production-ready until those gates are resolved.
## Local live-data recovery audit — 2026-09-28

The local SEBI Public Issues sync fetched 25 recent official filing records with document links into the isolated SQLite preview. The member IPO page shows them under Recent SEBI filings with application details under review. Its canonical IPO list still has no current real provider-derived IPO: the available NSE watch and SEBI metadata lack verified lot and allotment facts. This is a data/rights gate, not a frontend fetch failure. The full audit, source permissions and diagnostic commands are in `docs/LIVE_DATA_AUDIT.md` and `docs/DATA_PROVIDERS.md`. No AWS deployment or resource modification occurred.

`bash scripts/check.sh` passed 319 backend, 22 frontend and one Android test, with the Planner matrix and all configured lint, type, build and migration gates. A fresh local browser rendered the 11 saved NSE watch entries and 25 SEBI filing links, including Runwal Enterprises' RHP PDF. The canonical/planner count was 0 because lot and allotment facts remain unverified. The Founder Live Data page now persists SEBI attempt/success, record counts, safe error and enable state. Use `provider_status`, `sync_ipo_data --provider=sebi`, `show_live_ipos`, `show_ipo_conflicts` and `sync_gmp` for local diagnostics. Other provider commands explain their legal/credential gate. The earlier statement that the NSE command performs a network request is superseded: `refresh_nse_ipo_feed` now requires `--file` and `--observed-at`.
