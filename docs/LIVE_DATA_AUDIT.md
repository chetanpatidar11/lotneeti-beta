# Live data audit — 2026-09-28

## Latest local audit — 11 current issues ready

The latest official saved NSE list has **eight NSE Mainboard and three NSE EMERGE issues**. NSE Issue Information detail and official NSE-linked RHP/SEBI documents supplied every planner-required fact. The NSE list is discovery only. `show_live_ipos` after enrichment reports **11 READY, 0 REVIEW_REQUIRED, 11 published/plannable** in the isolated local preview. GREENASIA, BMISL and HIMALAYAN are NSE EMERGE per their RHP covers, with NSE designated and BSE `NOT_APPLICABLE`; no BSE cross-check is needed. AONESTEELS is dual listed with BSE designated according to its RHP. The second local publication run returned `unchanged` for all 11. No AWS deployment occurred.

Current discovery counts: NSE Mainboard **8**, NSE EMERGE **3**, BSE Mainboard **0**, BSE SME **0**. BSE's public interface did not yield a permissioned automatic current feed here; saved official discovery/detail import and parser tests exist, but no current BSE value has been asserted. Current GMP source count is **0**, current GMP values **none**, and all 11 issues show **GMP unavailable**. IPO Guru v2's 10/day evaluation tier cannot support 15-minute polling; no key or other permitted zero-cost source was configured. Founder manual GMP entry remains available. The 00:00 IST daily IPO job and 15-minute GMP job are scheduled in code; the GMP job makes zero external requests in this state.

Current per-symbol result: AONESTEELS lot 37/allotment 2026-09-29, GREENASIA 1600/2026-09-29, MONEYVIEW 441/2026-09-29, ACEVECTOR 468/2026-09-30, BMISL 1200/2026-09-30, GERMAN 107/2026-09-30, HIMALAYAN 1200/2026-09-30, ORIENTCABL 55/2026-09-30, RUNWALENTR 49/2026-09-30, SHAHINVEST 85/2026-10-01 and SRIT 115/2026-10-01. All lots came from NSE detail; the dates came from NSE RHP or SEBI RHP as recorded by `show_live_ipos`. The command prints price band, dates, source states, field provenance and planner state for each issue. `bash scripts/check.sh` passed 344 backend, 27 frontend and one Android test, and the full Planner matrix. This is **local state only**; the older AWS beta described in historical handoff sections still serves an earlier build.

## Previous 8/3 local D03 result — superseded by the latest audit

The previous audit described an **earlier discovery-only state**. On 2026-09-28, a Founder-triggered local pass fetched NSE issue detail and NSE-linked official RHPs for all 11 saved active/forthcoming issues, then matched the available recent SEBI RHPs. NSE `/api/ipo-current-issue` supplied discovery; `/api/ipo-detail?symbol=…&series=…` supplied symbol/company, issue period, price band, Bid Lot or SME Lot Size, minimum quantity, issue size/type, face/tick, registrar and RHP links. Official RHP/PDF timetable labels supplied dates. This data and the complete local SQLite preview are **not deployed to AWS**. No GMP source was introduced.

Latest `show_live_ipos` result, formatted as `symbol: lot [source]; allotment [source]; upper price [source]; local state`:

- AONESTEELS: 37 [NSE_DETAIL]; 2026-09-29 [NSE_RHP]; ₹405 [NSE_DETAIL]; PUBLISHED/READY.
- GREENASIA: 1,600 [NSE_DETAIL]; 2026-09-29 [NSE_RHP]; ₹90 [NSE_DETAIL]; REVIEW_REQUIRED/NOT_PUBLISHED — BSE detail unverified.
- MONEYVIEW: 441 [NSE_DETAIL]; 2026-09-29 [SEBI_RHP]; ₹34 [NSE_DETAIL]; PUBLISHED/READY.
- ACEVECTOR: 468 [NSE_DETAIL]; 2026-09-30 [SEBI_RHP]; ₹32 [NSE_DETAIL]; PUBLISHED/READY.
- BMISL: 1,200 [NSE_DETAIL]; 2026-09-30 [NSE_RHP]; ₹110 [NSE_DETAIL]; REVIEW_REQUIRED/NOT_PUBLISHED — BSE detail unverified.
- GERMAN: 107 [NSE_DETAIL]; 2026-09-30 [NSE_RHP]; ₹139 [NSE_DETAIL]; PUBLISHED/READY.
- HIMALAYAN: 1,200 [NSE_DETAIL]; 2026-09-30 [NSE_RHP]; ₹103 [NSE_DETAIL]; REVIEW_REQUIRED/NOT_PUBLISHED — BSE detail unverified.
- ORIENTCABL: 55 [NSE_DETAIL]; 2026-09-30 [SEBI_RHP]; ₹272 [NSE_DETAIL]; PUBLISHED/READY.
- RUNWALENTR: 49 [NSE_DETAIL]; 2026-09-30 [NSE_RHP]; ₹305 [NSE_DETAIL]; PUBLISHED/READY. An earlier SEBI PDF parse failed safely; a later official issuer-search document succeeded, while the linked NSE RHP supplies the selected date.
- SHAHINVEST: 85 [NSE_DETAIL]; 2026-10-01 [SEBI_RHP]; ₹167 [NSE_DETAIL]; PUBLISHED/READY.
- SRIT: 115 [NSE_DETAIL]; 2026-10-01 [NSE_RHP]; ₹130 [NSE_DETAIL]; PUBLISHED/READY.

All 11 have zero missing planner-required fields after detail/document enrichment. The three BSE-flagged SME rows remain under review solely because current BSE issue details could not be cross-checked. BSE public discovery yielded an app shell and direct DisplayIPO was inaccessible; the offline parser and equal/conflicting lot tests do not constitute live BSE verification. The SEBI match now searches the official repository by issuer beyond the recent-25 index; exhaustive pagination of large issuer result sets remains open. Valid NSE-linked RHPs supplied the required timetable where SEBI did not match. No current date or price was guessed; optional failures do not erase cached valid facts. A full SEBI search and permissioned BSE detail access remain source-coverage gaps.

The local authenticated IPO API returned eight published real issues and 11 watch observations. `http://127.0.0.1:3002/ipos` rendered the eight cards and three review rows (HTTP 200); `/plan` returned 200. The source label now distinguishes fetched time from a genuine source update time. `bash scripts/check.sh` passed 335 backend, 27 frontend and one Android test, plus lint/type/migration/build gates. Older sections below are retained as historical investigation notes; their zero-plannable local conclusion no longer applies to this preview.

## Path and current failure

`ManualIPOProvider` and `NormalizedExchangeIPOProvider` normalize complete records into `IPORecord`. `record_exchange_snapshot` requires an existing canonical IPO and stages immutable data on a disabled `IPOSourceLink`. Approved links affect `effective_ipo_values` dynamically, but never create or publish an IPO. `published_ipos` gates the member IPO API, workspace selection and planner snapshot. The Next.js IPO page reads that API plus a separate read-only feed watch. Thus a valid exchange observation cannot reach planning unless a complete IPO is created/published and its link is approved. Founder entry is currently the only creation path.

The saved NSE current-issue response has 11 real rows from 2026-09-27/28. Eight have price bands; all lack lot size and allotment date. Three BSE-flagged SME rows lack price bands. They are correctly displayed only as incomplete watch entries. No GMP provider fetches data. The existing `refresh_nse_ipo_feed` command can call an undocumented NSE website endpoint and must be restricted to approved offline imports; it must not become a production scheduled feed.

## Provider and integration inventory

- **NSE:** manual/offline normalized exchange adapter and an undocumented website JSON watch adapter. No licensed NSE Data & Analytics client, credentials, or scheduler. The official MCP is informational/noncommercial only and no IPO-capable tool has been verified. Production website collection is disallowed by NSE terms.
- **BSE:** normalized offline adapter only. The public issue URL previously returned 403; a later local request returned only a generic app shell, not issue records. No permissioned automated website path or Self Data Feed account/schema was found. Self Data Feed advertises limited trial access, with registration/KYC, plan, agreement and possible payment steps. IPO coverage is unverified.
- **SEBI:** normalized offline adapter only. Public Issues index and documents are reachable; filing metadata can be linked, but prices, lot and dates need reliable document extraction/review. Its website policy allows direct links; reproduction of website material requires permission.
- **GMP:** manual observations and consensus work; InvestorGain/IPOWatch fetchers are absent. IPOWatch terms grant personal noncommercial access and restrict copying/redistribution. InvestorGain's own terms expressly prohibit unauthorized commercial scraping, copying and redistribution even though robots allows pages. IPO Guru's free API is evaluation/noncommercial only and needs a manually issued key. Indian API advertises free commercial API use, but its IPO endpoint plan scope and third-party data rights could not be verified without an account. None is enabled for scheduled GMP ingestion.

## Data behavior

- Approved snapshot merge preserves last valid cached fields on missing values, exchange conflicts or invalid mixed facts. Manual corrections win and Resume Automatic re-resolves approved sources.
- GMP uses the newest observation per enabled source, 24-hour default freshness, median and 5-percentage-point conflict threshold from Founder-editable settings. Missing GMP stays null. History remains immutable. SEBI sync now persists last attempt/success, fetched/saved counts, enabled state and a safe error class; NSE/BSE lack licensed feed health because those clients cannot run.
- At audit start, the public API exposed raw IPO conflict/provenance fields and the member page rendered them. This run removed those fields from the member API/page; Founder Admin remains the review surface. The page still cannot turn incomplete observations into complete planning records.
- At audit start, Celery Beat scheduled only recurring debits. This run added a six-hour SEBI filing sync and 15-minute stale health refresh, plus isolated task entry points for official IPO/GMP sources that report missing rights rather than fetching them. Automated canonical publication remains absent because no complete rights-cleared source is configured.

## Legal and credential gates

NSE website terms prohibit systematic automated collection; NSE Data & Analytics requires an agreement for commercial use and controls redistribution. NSE MCP expressly excludes commercial use. BSE Self Data Feed needs registration and contract review; IPO coverage is not established. SEBI direct links are allowed, but copied material needs permission. IPOWatch and InvestorGain terms block an automatic commercial feed. IPO Guru's free tier is evaluation only. No paid plan or API is activated.

## Current real issue verification

At approximately 06:49 Asia/Dubai on 2026-09-28, the local `sync_ipo_data --provider=sebi` command fetched the official SEBI Public Issues index and 25 linked filing pages. It stored 25 distinct current filing records and direct official PDF links in the isolated `/private/tmp/lotneeti-local-preview.sqlite3` database. Examples include **Runwal Enterprises Limited — RHP — filed 2026-09-24** and **Moneyview Limited — Corrigendum to RHP and Price Band — filed 2026-09-23**. The issuer, document type, filing date and PDF URL came from SEBI; prices, lot, dates, issue size and exchanges were **not** inferred. GMP source: none. All 25 are `REVIEW_REQUIRED` and exposed as filing links on the IPO page, not as open applications.

The local preview also contains 11 earlier saved NSE watch rows, but zero rows can be proved end-to-end as canonical published/plannable from either feed because required lot and allotment facts are absent. The current canonical API, workspace selection and planner snapshot therefore have **zero current real source-derived IPOs** in this preview. A real issue can enter that path only after a rights-cleared source supplies complete validated facts and safe publication. No value was guessed to close the gap. The watch API marks observations older than 24 hours stale, and the page does not present their saved "Active" status as live.

The SEBI sync uses an identifiable user agent, a single index request plus at most 25 same-host document-page requests, a 15-second request timeout and a 1 MB response limit. It stores metadata/links, not PDF contents. The previous undocumented NSE website fetch was removed from the refresh command; its saved-file import remains available. BSE and free GMP sites are not contacted by scheduled jobs.
