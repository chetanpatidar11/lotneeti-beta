# 05_Feature_Ticket_Backlog_v2

LotNeeti Feature Ticket Backlog

Implementation tickets aligned to approved Planner v2

Version 2.1 • Development backlog • September 2026

# 1. Backlog Conventions

| Field | Meaning |
| --- | --- |
| Priority | P0 = required for founder beta; P1 = required for invited/public beta; P2 = later/scale. |
| Points | Relative estimate: 1,2,3,5,8. |
| Acceptance | Concise measurable outcome; planner tickets additionally require matching Planner v2 tests. |

# 2. Epic A - Foundation, Accounts & Workspaces

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| A01 | Create Django project and settings split | P0 | 3 | - | Local dev runs with PostgreSQL/Redis and environment-based settings. |
| A02 | Create Next.js TypeScript frontend | P0 | 3 | - | Web app builds and calls versioned API health endpoint. |
| A03 | Workspace and membership models | P0 | 5 | - | OWNER/OPERATOR/VIEWER memberships enforce workspace scope. |
| A04 | Founder Admin platform role | P0 | 3 | - | Founder can access staff controls without granting platform rights to Workspace Owners. |
| A05 | Email/Google beta authentication | P0 | 5 | - | User can sign in and persist a trusted session. |
| A06 | Admin TOTP MFA | P0 | 5 | - | Founder/admin login requires second factor. |
| A07 | Global audit event service | P0 | 5 | - | Privileged/sensitive events can write actor, object, action, metadata, timestamp. |
| A08 | Feature flag framework | P1 | 3 | - | Workspace/platform flags can gate unfinished capabilities. |

# 3. Epic B - Investor, Demat, Bank & UPI Master

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| B01 | Investor CRUD | P0 | 3 | - | Create/edit/activate investor with PAN and planning priority. |
| B02 | PAN encryption and lookup hash | P0 | 5 | B01 | PAN stored encrypted; duplicate lookup works without plaintext index. |
| B03 | Demat CRUD | P0 | 3 | - | Investor supports CDSL/NSDL DP/client data and active state. |
| B04 | Bank account CRUD | P0 | 5 | - | Create bank with owner, masked/encrypted account number, balance and policy. |
| B05 | UPI CRUD | P0 | 3 | - | UPI linked to bank, active/verified state and optional limit overrides. |
| B06 | Applicant priority UI | P0 | 2 | - | User can set/reorder numeric priority; lower number clearly explained. |
| B07 | Account Excel import parser | P0 | 5 | - | Uploaded sample-format workbook imports investor/demat/bank/UPI with row errors. |
| B08 | Import preview/auto-import UI | P0 | 5 | B07 | Upload automatically persists all valid rows; masked preview and row errors remain visible, and invalid rows are skipped. |
| B09 | Investor active/inactive handling | P0 | 2 | - | Inactive applicant is excluded from automatic planning. |

# 4. Epic C - Balances, Recurring Debits & Funding Preferences

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| C01 | Balance + operation | P0 | 3 | - | Adding ₹X updates current balance and writes history entry. |
| C02 | Balance - operation | P0 | 3 | - | Removing ₹X updates current balance and writes history entry. |
| C03 | Set Balance operation | P0 | 3 | - | Exact set stores resulting balance and history. |
| C04 | Recent balance changes UI | P0 | 2 | - | Bank screen shows understandable +/- history without ledger terminology. |
| C05 | Recurring debit model | P0 | 3 | - | Store bank, name, amount, recurrence, next date, active/paused. |
| C06 | Recurring debit scheduler | P0 | 5 | C05 | Each due occurrence posts once and advances next due date. |
| C07 | Recurring debit CRUD UI | P0 | 3 | - | User can create/edit/pause/delete recurring expense. |
| C08 | FundingPreference model | P0 | 3 | - | Beneficiary has ordered enabled preferred cross-funding banks. |
| C09 | Funding preference UI | P0 | 3 | - | User can rank preferred funding accounts per applicant. |
| C10 | Cross-funding policy hierarchy | P0 | 5 | - | Effective policy resolves platform, bank, workspace, plan and manual context. |

# 5. Epic D - IPO, GMP & Quick Analysis

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| D01 | IPO canonical model | P0 | 5 | - | Stores issue facts, price/lot/dates/allotment/status and source provenance. |
| D02 | Manual IPO provider | P0 | 3 | - | Founder can create/update IPO data through provider interface. |
| D03 | Provider adapter interface | P0 | 3 | - | IPO sources normalize into canonical DTOs. |
| D04 | GMP observation model | P0 | 3 | - | Store source, value, timestamps and provenance history. |
| D05 | Manual GMP provider | P0 | 3 | - | Founder can enter time-stamped GMP observations during beta. |
| D06 | GMP trend API/UI | P0 | 3 | - | IPO shows current GMP %, ₹ value and history/trend. |
| D07 | Workspace GMP threshold | P0 | 2 | - | Workspace stores configurable auto-select threshold; founder can set 20%. |
| D08 | IPO manual APPLY/SKIP decision | P0 | 5 | - | Manual decision overrides threshold and persists until reset. |
| D09 | Reset IPO decision to automatic | P0 | 2 | - | User can return to threshold-based behavior. |
| D10 | IPO mode selection | P0 | 3 | - | Per selected IPO: Retail Only, Retail+sHNI, sHNI Preferred, Custom. |
| D11 | IPO quick company summary | P1 | 5 | - | Show concise business, financial and risk summary from stored content. |
| D12 | AI summary pipeline | P1 | 8 | - | Queue once per document/version; store draft, metadata and review state. |
| D13 | IPO field override model | P1 | 5 | - | Manual override stays separate from source value and can resume auto later. |
| D14 | GMP provider health admin | P1 | 5 | - | Admin sees last success/error, can enable/disable and override with expiry. |

# 6. Epic E - Planner v2 Core

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| E01 | Planner immutable DTO package | P0 | 5 | - | Snapshot types contain no ORM objects and serialize deterministically. |
| E02 | Quote-size calculator | P0 | 3 | - | Retail=1 lot; min sHNI is smallest whole-lot amount > ₹2L. |
| E03 | 24-hour rolling-limit tracker | P0 | 5 | - | Counts/amounts respect UPI+bank defaults and cancellation rule. |
| E04 | Cash-at-cutoff timeline | P0 | 8 | - | Calculates balance minus blocks/planned/debits plus eligible releases. |
| E05 | Owner baseline reserve calculation | P0 | 8 | - | Cross-funding protects owner baseline needs across overlapping selected IPOs. |
| E06 | Final selected IPO ordering | P0 | 3 | - | Higher GMP first; equal GMP uses earlier cutoff then stable ID. |
| E07 | Baseline Retail coverage phase | P0 | 8 | - | Per IPO, cover eligible PANs in applicant-priority order with one row max. |
| E08 | Same-name wallet preference | P0 | 5 | - | Own/same-name feasible wallet preferred but does not hard-ban cross-funding. |
| E09 | Preferred cross-funder ranking | P0 | 5 | - | Configured FundingPreference order is respected after own wallet. |
| E10 | Retail stranded-cash preference | P0 | 5 | - | Small retail-only cash preferred when stronger rules equal. |
| E11 | sHNI upgrade phase | P0 | 8 | - | Retail→sHNI only; min quote; no duplicate PAN row. |
| E12 | sHNI Preferred maximum-count loop | P0 | 8 | - | Continues feasible minimum-sHNI upgrades until none remain. |
| E13 | Bounded repair/rehome | P0 | 8 | - | May move unlocked Retail rows; local change rolls back if any displaced row cannot rehome. |
| E14 | Owner-affinity cleanup | P1 | 5 | - | Same-size unlocked swaps improve owner mapping without changing totals. |
| E15 | Locked-row processing | P0 | 5 | - | Locked manual row is retained exactly and marked blocking when infeasible. |
| E16 | Planner explanation builder | P0 | 5 | - | Every automatic row gets ordered human-readable reason codes/data. |
| E17 | Independent final cash/limit audit | P0 | 8 | - | Replays plan from scratch and blocks any double spend/limit breach. |
| E18 | Planner determinism hashing | P0 | 5 | - | Persist planner version + input hash; identical inputs yield identical logical plan. |
| E19 | Planner run persistence | P0 | 5 | - | Save PlanRun, rows, warnings and snapshot metadata transactionally. |
| E20 | Planner preview API | P0 | 5 | - | POST snapshot/preferences returns proposal without mutating application state. |

# 7. Epic F - Plan Editor & Validation

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| F01 | Plan mapping table | P0 | 8 | - | Desktop/mobile review shows IPO, applicant, category, lots, demat, bank, UPI, funding/status/lock. |
| F02 | Edit applicant | P1 | 5 | - | Changing applicant revalidates duplicate PAN and eligibility. |
| F03 | Edit category/lots | P0 | 5 | - | Amount recalculates; Retail/sHNI exclusivity enforced. |
| F04 | Edit demat | P0 | 3 | - | Only active/allowed demats can finalize. |
| F05 | Edit bank/UPI | P0 | 5 | - | Selector shows own/preferred/fallback and immediate cash/limit warnings. |
| F06 | Lock/unlock row | P0 | 3 | - | Locked rows persist unchanged through re-plan. |
| F07 | Re-plan unlocked rows | P0 | 5 | - | Planner preserves locks and recalculates remaining resources. |
| F08 | Blocking vs warning presentation | P0 | 3 | - | User cannot export blocking plan; warnings remain visible. |
| F09 | Why this bank explanation | P1 | 3 | - | User can open short reason summary for automatic mapping. |

# 8. Epic G - Exports

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| G01 | Export adapter interface | P0 | 3 | - | Plan rows map through named versioned export adapters. |
| G02 | Generic CSV export | P0 | 3 | - | Valid plan exports deterministic CSV. |
| G03 | Sample/broker Excel adapter | P0 | 5 | - | Generate workbook matching agreed template mapping. |
| G04 | Private S3 export storage | P0 | 3 | - | Generated files private; short-lived authorized download URL. |
| G05 | Export version snapshot | P0 | 3 | - | Record plan version/hash used for each export. |

# 9. Epic H - Application, Block & Allotment Tracking

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| H01 | Application status model | P0 | 5 | - | Planned/submitted/blocked/result states and timestamps persist. |
| H02 | Mark submitted/blocked UI | P0 | 3 | - | Blocked amount appears in dashboard without reducing Balance. |
| H03 | Not-allotted action | P0 | 3 | - | Releases block; Balance unchanged. |
| H04 | Allotted action | P0 | 5 | - | Deduct actual cost and release full block atomically. |
| H05 | Partial allotment handling | P0 | 5 | - | Deduct actual cost and release remainder. |
| H06 | Expected next-day release rule | P0 | 3 | - | Future planner may reuse from day after allotment date until actual status overrides. |
| H07 | Application history view | P1 | 3 | - | Timeline shows submitted, block, result and debit/unblock events. |

# 10. Epic I - Portfolio & Profit

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| I01 | Sale entry model/UI | P0 | 3 | - | Record quantity, price, date, charges. |
| I02 | Realized P&L calculator | P0 | 3 | - | Compute proceeds-cost-charges and ROI. |
| I03 | IPO/investor/workspace profit views | P1 | 5 | - | Aggregate realized results across useful dimensions. |

# 11. Epic J - Frontend Foundation & UX

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| J01 | Responsive app shell/navigation | P0 | 5 | - | Mobile and desktop primary tabs implemented. |
| J02 | Dashboard capital cards | P0 | 5 | - | Balance, Blocked, Planned, Available cards match simple prototype direction. |
| J03 | Dashboard operations cards | P0 | 3 | - | Active IPOs, applications, pending mandates, allotment wins, gains. |
| J04 | IPO card/list UI | P0 | 5 | - | Shows issue facts, GMP %, selection state and mode. |
| J05 | Plan creation two-column desktop layout | P0 | 5 | - | Selected IPOs left; strategy/capital context right; mobile stacks cleanly. |
| J06 | Plain-language validation copy | P0 | 3 | - | No raw backend exception codes shown to end users. |
| J07 | Indian number/date formatting | P0 | 2 | - | ₹ and Indian grouping used consistently. |
| J08 | Accessibility baseline | P1 | 3 | - | Labels, keyboard flow, focus states, icon+text warnings, adequate tap targets. |

# 12. Epic K - Founder Admin & Content Governance

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| K01 | Platform admin navigation | P0 | 3 | - | Founder reaches IPO/GMP/users/planner/security from one staff surface. |
| K02 | IPO exception dashboard | P1 | 5 | - | Shows stale/conflicting/missing fields requiring review. |
| K03 | IPO override editor | P1 | 5 | - | Source vs override values, reason and resume-auto control. |
| K04 | GMP source/override editor | P1 | 5 | - | Enable/disable, correction, expiry, freshness and reason. |
| K05 | AI content review/editor | P1 | 5 | - | Edit published draft while retaining original/history. |
| K06 | Planner policy editor | P1 | 5 | - | Effective-dated defaults/bank policies with reason/audit. |
| K07 | Support workspace lookup | P1 | 3 | - | Metadata/redacted diagnostics without default full sensitive reveal. |

# 13. Epic L - Security, AWS & DevOps

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| L01 | Workspace isolation test suite | P0 | 5 | - | Cross-workspace CRUD attempts fail across sensitive APIs. |
| L02 | Sensitive-field masking/encryption | P0 | 8 | - | PAN/bank values encrypted and masked by default. |
| L03 | Export authorization tests | P0 | 3 | - | Only authorized workspace member can generate/download export. |
| L04 | Rate limiting | P1 | 5 | - | Auth/import/export/planner/admin abuse paths limited. |
| L05 | Security headers/HTTPS config | P0 | 3 | - | Production-like beta uses HTTPS and secure headers/cookies. |
| L06 | Nightly PostgreSQL S3 backup | P0 | 5 | - | Automated encrypted/compressed backup with retention. |
| L07 | Restore test procedure | P0 | 3 | - | Documented restore is successfully tested before inviting external beta users. |
| L08 | AWS budget alerts | P0 | 2 | - | Alerts configured before beta resources are left running. |
| L09 | Structured application logging | P0 | 3 | - | Request/job/provider errors searchable without logging sensitive plaintext. |
| L10 | CI pipeline | P0 | 5 | - | Lint/tests/build run on each main PR; planner P0 suite gates merge. |
| L11 | EC2 beta deployment automation | P0 | 5 | - | Repeatable deploy of Django, Celery, Redis, PostgreSQL and Nginx. |
| L12 | S3 private bucket policies | P0 | 3 | - | No public access; least-privilege application/backup permissions. |

# 14. Epic M - Testing & Beta Readiness

| ID | Ticket | Pri | Pts | Depends | Acceptance |
| --- | --- | --- | --- | --- | --- |
| M01 | Import Planner v2 120-case test matrix | P0 | 8 | - | All P0 scenarios represented as executable tests. |
| M02 | Create founder 17-PAN fixture | P0 | 5 | - | Sanitized realistic fixture covers banks/UPIs/priorities/funding preferences. |
| M03 | Create 15-25 historical golden plans | P0 | 8 | - | Expected mappings documented; intentional v2 differences approved. |
| M04 | Planner regression snapshot suite | P0 | 5 | - | Identical fixtures produce stable plan results across releases. |
| M05 | End-to-end beta scenario | P0 | 8 | - | IPO select → plan/edit/lock → export → block → allotment → sale/P&L passes. |
| M06 | Beta feedback/analytics events | P1 | 3 | - | Track activation, plan generation, edits, exports, allotment and P&L completion without sensitive payloads. |

# 15. Recommended Delivery Sequence

1.  Sprint 0: A01-A07, L08/L10 plus local infrastructure and security baseline.

2.  Sprint 1: Investor/demat/bank/UPI + balance controls + account import.

3.  Sprint 2: IPO/GMP manual providers + selection decisions + planner DTO/cash/limit foundation.

4.  Sprint 3: Retail coverage + funding preferences + owner protection + plan editor.

5.  Sprint 4: sHNI + repair/audit + exports + full Planner v2 P0 suite.

6.  Sprint 5: tracking/allotment/profit + dashboard + founder admin.

7.  Beta 0: founder 17-PAN golden scenarios; do not invite users until planner results are trusted.

8.  Beta 1/2: usability/security/data-provider improvements, then invited users.

# 16. Planner Definition of Done

- All applicable Planner v2 P0 tests pass.

- No duplicate PAN/category row can exist for one IPO.

- Final audit independently confirms cash and rolling limits.

- Every automatic row has an explanation; every infeasible lock remains visible.

- Same inputs/settings produce the same logical plan.

- Founder historical golden scenarios match approved expected results or document intentional differences.

Total tickets in this backlog: 118
