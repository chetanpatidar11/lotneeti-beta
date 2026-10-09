# LotNeeti data providers — founder beta

## Current provider decision — 2026-10-03

The Founder selected **InvestorGain as the single IPO and GMP source**. The scheduled and Founder Admin refresh use its authorised report endpoint for active/upcoming issue name, category, price, lot, open/close, basis-of-allotment, listing and GMP fields. One response creates/updates the InvestorGain-backed IPOs and appends GMP observations. Rows missing a planner-required field are skipped rather than guessed.

NSE, BSE and SEBI jobs are no longer scheduled or exposed as Founder Admin refresh actions. Their existing code and historical records are retained for audit/recovery but are not called by the active source workflow. Founder Admin can refresh InvestorGain repeatedly at any time; automatic jobs remain at 00:01 and hourly 09:00–19:00 Asia/Kolkata.

## Earlier local provider state — 2026-10-02

The isolated local preview has **11/11 current NSE issues READY and plannable**: eight NSE Mainboard and three NSE EMERGE. All have NSE detail and official document facts; no BSE record is required for an NSE EMERGE issue. GREENASIA, BMISL and HIMALAYAN are NSE EMERGE with NSE designated according to their official RHP covers, despite an `isBse` flag in the NSE list. AONESTEELS is dual listed and its official RHP designates BSE. MONEYVIEW Bid Lot **441** and AONESTEELS Bid Lot **37** are current NSE detail results, not constants in the provider. The local canonical publisher was rerun twice and the second pass made zero changes. None of these changes has been deployed to AWS.

Independent BSE Mainboard and BSE SME saved-feed discovery, issue-detail parsing and official document normalization are implemented. A permitted automatic BSE discovery feed has not been obtained; current BSE live discovery is **0/0**, and no cross-exchange agreement has been claimed. When an official BSE record is supplied, `import_bse_ipo_discovery` and `import_bse_ipo_detail` retain it, and a BSE-only SME can become READY without NSE. The scheduled coordinator returns `PERMISSION_REQUIRED` for BSE while processing other sources.

Celery Beat schedules the NSE coordinator at **00:01 Asia/Kolkata** and one complete NSE refresh hourly at **09:00 through 19:00**. A complete run may fetch the discovery list and any uncached issue details or documents. InvestorGain GMP is scheduled at **00:01** and hourly at **09:00 through 19:00**. Persisted per-provider slot guards prevent manual or duplicate runs outside those licensed slots. Daily NSE requests require `LOTNEETI_NSE_SOURCE_RIGHTS_REFERENCE` and `LOTNEETI_IPO_SOURCE_CACHE_DIR` in the private server environment; the same pipeline is called by Founder Admin and `manage.py sync_ipo_data`. Only the isolated local test database can use automatic local canonical publication. GMP exits before a request when there is no relevant IPO and does not run on customer requests.

The Founder confirmed a licensed InvestorGain cadence of one request per hourly slot from 09:00 through 19:00 Asia/Kolkata plus one request at 00:01; retain the license outside Git. The integration uses the approved report endpoint with an identifying LotNeeti user agent, `Accept`, `Origin` and `Referer` headers only. It stores raw GMP observations with a stable report row ID, detail URL, source-provided `Updated-On` value where parseable, fetch time and payload hash. It does not use browser client-hint headers, cookies, authentication, CAPTCHA bypasses or member-request fetching. InvestorGain is one unofficial source in the existing GMP consensus and does not provide canonical IPO facts. Founder manual entry remains available and K02's editable 24-hour/5-point median/conflict policy remains active.

## Previous D03 8/3 result — superseded locally (2026-09-28)

The earlier list-only conclusion below is superseded **for the current local preview**. The NSE current-issue JSON is discovery, not a complete issue record. The Founder-triggered local `enrich_live_ipos` pass obtained official NSE `/api/ipo-detail?symbol=…&series=…` responses and NSE-linked RHPs for all 11 current symbols. The NSE Issue Information detail provides symbol, company, issue period, price band, Bid Lot or SME Lot Size, minimum order quantity, issue size/type, face value, tick size, discount, market timings, registrar/contact, BRLM, sponsor bank, categories and document links when present. Bid Lot/Lot Size maps to canonical `lot_size`; minimum quantity is checked for consistency. Source update time is recorded only if the response explicitly supplies it; fetch and snapshot times are separate. [NSE Issue Information](https://www.nseindia.com/market-data/issue-information?series=EQ&symbol=MONEYVIEW&type=Active).

Official NSE RHP ZIP/PDF and matched SEBI Public Issues RHP/PDF documents are searched for explicit indicative timetable labels: open, close, allotment, refund/unblock, demat credit and listing. The extractor saves the document URL/type/date, evidence excerpt/page, extraction time and review state. An applicable later corrigendum overrides only dates it explicitly changes. It never derives an allotment date from list timestamps. The founder-triggered pass searches the official SEBI Public Issues index by issuer, beyond the recent 25; exhaustive pagination for an issuer with more than one result page remains open. [SEBI Public Issues](https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&smid=12&ssid=15).

The official [BSE Public Issues](https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx) page yielded only an app shell locally, and direct DisplayIPO detail was inaccessible. An offline BSE detail provider/parser maps **Market Lot** to lot size and checks Minimum Bid Quantity, with tests from synthetic permitted fixtures; automatic BSE fetch and current cross-exchange verification remain disabled until a permitted detail source is available. Equal NSE/BSE lots can mark multiple-official-source verification; different lots are preserved and flagged for Founder review. GREENASIA, BMISL and HIMALAYAN remain REVIEW_REQUIRED for this exact reason despite having complete NSE/detail/RHP facts.

The isolated local SQLite preview has eight published READY EQ issues and three unpublished BSE-flagged review issues. Moneyview lot **441** and A-One Steels lot **37** came from current official NSE detail, with allotment **2026-09-29** from SEBI RHP and NSE RHP respectively. The full per-issuer source/field report is in `show_live_ipos` and [`LIVE_DATA_AUDIT.md`](LIVE_DATA_AUDIT.md). `/ipos` reads saved data and now displays the eight ready issues as real cards; no customer request fetches NSE/BSE/SEBI. The AWS beta still serves the earlier list-only build; this D03 work was **not deployed**. GMP remains unavailable without a separate permitted provider.

Local repeat (Founder-triggered, isolated test settings only): `LOTNEETI_TEST_DB=/private/tmp/lotneeti-local-preview.sqlite3 .venv/bin/python backend/manage.py enrich_live_ipos --saved-dir /private/tmp --fetch --refresh-discovery --settings=config.settings.test`, then `LOTNEETI_TEST_DB=/private/tmp/lotneeti-local-preview.sqlite3 .venv/bin/python backend/manage.py show_live_ipos --settings=config.settings.test`. `publish_ready_ipos --rights-reference <founder-recorded-reference>` publishes only complete READY rows in test SQLite; it cannot publish to production. Fetched originals stay outside Git. `bash scripts/check.sh` passed: 335 backend, 27 frontend, one Android test and all other configured gates.

## Verified source status — 2026-09-28

| Provider | Data | Method | Cost | Automated? | Commercial/public use status | Enabled now? | Credentials | Last verified |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [NSE Data & Analytics](https://www.nseindia.com/static/nse-data-and-analytics/data-information-vending) | Market/corporate data; IPO feed scope needs confirmation | Contracted feed | Paid/quote | Contract dependent | [Agreement controls use and redistribution](https://www.nseindia.com/static/market-data/nse-data-policy) | No | Agreement, endpoint/schema, entitlement | 2026-09-28 |
| [NSE MCP](https://www.nseindia.com/nse-mcp) | Market data; IPO tool unverified | Official MCP | Free informational | Local inquiry only | Explicitly noncommercial; no public deployment | No | MCP connection | 2026-09-28 |
| [NSE website current issue JSON](https://www.nseindia.com/api/ipo-current-issue) | Discovery only; detail and RHP are separate | Website endpoint | Free to view | Founder-permission-gated local job | [NSE default terms restrict systematic collection](https://www.nseindia.com/static/nse-terms-of-use); Founder attested separate written permission | Local preview only, with private rights reference | Scope record and private cache | 2026-09-28 |
| [BSE Self Data Feed](https://marketdata.bseindia.com/) | EOD/reference/corporate data; IPO coverage unverified | Registered API/trial | Limited trial; price after agreement | Contract dependent | Redistribution terms require agreement review | No | Register, KYC, plan, agreement, feed schema | 2026-09-28 |
| [BSE public issues](https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx) | Issue summaries | Website | Free to view | No | Automated reuse unclear; list returned app shell and direct detail was inaccessible | No | Permission or manual import | 2026-09-28 |
| [SEBI Public Issues](https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&sm=&ssid=15) | Filing dates, issuers, document types and PDF links | Official HTML index | Free | Yes, within daily IPO sync | [Direct links allowed; reproduction requires permission](https://www.sebi.gov.in/website-policy.html) | Local index and document enrichment | None | 2026-09-28 |
| [InvestorGain](https://investorgain.in/) | GMP observations | Licensed report endpoint | Founder-approved beta use | Hourly 09:00–19:00 and once at 00:01 IST | License details remain outside Git | Local preview | No credential; private license record | 2026-10-02 |
| [IPOWatch](https://ipowatch.in/) | GMP | Website | Free to view | No | [Personal noncommercial license; copying/redistribution restricted](https://ipowatch.in/term-of-use/) | No | Separate license | 2026-09-28 |
| [IPO Guru API v2](https://www.ipoguru.in/ipo-gmp-details-developer-api) | IPO calendar/details and current GMP; history on paid tier | Authenticated API | Free evaluation, paid production | No in this app | Free tier [evaluation/noncommercial only](https://www.ipoguru.in/ipo-gmp-details-developer-api); paid plan needed for commercial use | No | Manually issued API key and production plan | 2026-09-28 |
| [Indian API IPO](https://dev.indianapi.in/) | IPO calendar/details; GMP coverage unverified | Authenticated API | Free plan exists, endpoint/plan scope unverified | No | [Marketplace terms allow commercial use](https://indianapi.in/legal/terms), but third-party rights and IPO plan scope need checking | No | Account/key and entitlement | 2026-09-28 |
| Founder manual | Complete IPO and GMP facts | Founder Admin | Free | Manual | Founder supplied | Yes | Founder MFA | 2026-09-28 |

### NSE official interface inventory

- [Data & Analytics products](https://www.nseindia.com/static/nse-data-and-analytics/data-information-vending): contracted real-time, end-of-day, historical and corporate products. Access/format depend on the agreement; IPO-specific fields and redistribution rights must be confirmed with NSE Data. Disabled, `LICENSE_REQUIRED`.
- [Paid corporate data](https://www.nseindia.com/static/market-data/corporate-data-subscription): leased-line corporate data and SFTP EOD announcements. Public page lists annual prices; neither is an identified complete IPO calendar feed. Disabled.
- [NSE MCP](https://www.nseindia.com/nse-mcp): published no-auth streamable HTTP endpoints for Bhavcopy and CM market data. The displayed tool groups cover trading prices, history and listings, with **no verified IPO/public-issue tool**. Its express noncommercial restriction rules it out for this public app; local Founder informational investigation only.
- [IPO page CSV download](https://www.nseindia.com/market-data/all-upcoming-issues-ipo), [IPO advertisements](https://www.nseindia.com/companies-listing/corporate-public-issue-advertisements), [issuer document RSS](https://www.nseindia.com/static/rss-feed), and [XBRL IPO filing specification](https://www.nseindia.com/static/companies-listing/xbrl-information): official website interfaces with possible public-issue metadata or documents. RSS is expressly offered for newsreader subscriptions. Automated commercial ingestion/redistribution permission and full planning coverage were not established; all remain disabled pending written scope.
- `/api/ipo-current-issue`: undocumented website JSON used for Founder-triggered local discovery and saved observations only. No production scheduled/customer-request fetch.

The SEBI index stores issuer/document metadata and direct official PDF links. No planning fact is inferred from a filing title; explicit document timetable extraction is separate. Its records appear under Recent SEBI filings on `/ipos` and in `/admin/live-data/`. The browser fetches saved local records only. The CLI entry is `python manage.py sync_ipo_data --provider=sebi`; Celery Beat includes it in the daily coordinated job. Founder Admin shows provider state from actual operations. NSE fetch is gated on the private rights reference and cache path; BSE and GMP report their access blockers without blocked website requests. No AWS or paid service was used in this local pass.

## K02 GMP policy — resolved locally on 2026-09-28

The Founder approved these editable beta defaults:

| Setting | Default | Founder Admin control |
| --- | --- | --- |
| GMP freshness limit | 24 hours | `/admin/gmp-policy/` |
| GMP source conflict threshold | 5.00 GMP percentage points, measured against the IPO's effective upper price band | `/admin/gmp-policy/` |

The MFA-gated Founder Admin policy page saves both values with a required reason and audit event. The IPO data exceptions page at `/admin/ipo-exceptions/` lists published IPOs with missing GMP, stale GMP sources or a GMP source conflict. The member IPO API and screen expose current GMP state, fresh source count, stale source count and conflict state.

For each enabled provider, the latest observation by observed/fetched time is its current candidate. A candidate is fresh when its observation age is at least zero and **less than** the configured limit; at exactly 24 hours under the default, it is stale. Stale and disabled sources do not enter consensus. An older observation from the same provider does not add another vote. All source records remain immutable and visible in history, including stale, disabled and conflicting observations.

With one or more fresh enabled candidates, current GMP is their exact median value per share. A conflict is marked when at least two candidates exist and `(highest raw GMP − lowest raw GMP) × 100 ÷ effective IPO upper price` is at least the configured threshold. A conflict remains visible while the median is served; the sources are not silently removed. The conflict comparison uses original source values, so a Founder correction does not hide disagreement.

An active Founder correction on a current fresh enabled observation takes precedence over the median. An active provider temporary value is the fallback correction when no observation correction is active. If several corrections are active, the most recently created observation correction wins; otherwise the most recently updated provider correction wins. Stale, disabled and superseded observations cannot supply a current correction. Correction expiry or resume returns current GMP to the fresh-source median. The raw source value and corrected effective value are both exposed in GMP history.

No fresh candidate means current GMP is unavailable. Automatic threshold selection then has no GMP input; manual APPLY/SKIP still outrank automation as Planner v2 requires. Planner snapshots resolve GMP at their explicit `as_of` time. The policy changes selection input and display; it does not alter the planner's financial calculations.

## D03 canonical IPO source preference — implemented locally

The Founder approved this order for IPO facts: active manual field correction; approved NSE value for an NSE issue; approved BSE value for a BSE issue; SEBI/RHP filing value; then the existing valid cached canonical value. A source link proves that the issue is associated with an exchange; the latest immutable snapshot on an approved link supplies only the fields explicitly present in its input. Every snapshot and original value remains stored.

When approved NSE and BSE snapshots both provide a field and agree, the value is accepted. When they differ, `ipo_source_conflict_fields` identifies the field, both source values remain available in Founder Admin, and the existing cached value remains effective until a Founder correction or source resolution. An active manual correction wins while the conflict remains visible. For facts explicitly stated in an RHP/prospectus (company, issue type, price band, lot, issue and allotment/listing dates), a matching SEBI snapshot remains the authoritative **provenance** even when the exchange repeats the same value. If the SEBI value differs from the selected exchange value, `ipo_document_disagreement_fields` flags that difference and retains both values for review. Administrative publication state is never taken from a feed.

Canonical snapshots are **review-only by default**. Migration `ipos.0011` adds `canonical_enabled`, a permission reference, approver and approval time to each source link; existing links remain disabled. Enabling a link requires Founder access and a documented rights reference through `set_canonical_source_enabled`. A temporary fetch failure inserts no new snapshot and therefore cannot clear the last approved source value or the cached canonical row. Disabling a link returns to other approved sources or the cached value. If combining source fields would create an invalid IPO, all source-derived fields fall back to the cached valid issue and `ipo_source_validation_blocked` marks it for Founder review. Planner and member API read the same effective values; the cached row itself is never overwritten by a sync.

For a **permitted normalized JSON record already obtained outside the app**, stage it without promotion:

```bash
.venv/bin/python backend/manage.py import_ipo_snapshot \
  --ipo-id '<canonical-ipo-uuid>' --source nse \
  --record-id '<official-stable-record-id>' \
  --observed-at '2026-09-28T10:00:00+05:30' \
  --file /private/tmp/approved-ipo-record.json
```

Use `--source bse` for a BSE record. The JSON must contain normalized `issuer_name`, `issue_type`, `lower_price`, `upper_price`, `lot_size`, `open_date`, `close_date` and `allotment_date`; optional fields are tracked as present or absent. This command makes no network request and leaves the record review-only. Do not put downloaded source data in Git without a confirmed right to do so.

### One-time current exchange watch import — 2026-09-28, local only

The Founder attested in chat that they have written permission to use publicly available exchange API data for the beta. The permission instrument and its exact scope were not supplied for independent review; retain it with the project records before any broader distribution. No paid provider or AWS service was used in this import.

A single response from NSE's [current-issue JSON endpoint](https://www.nseindia.com/api/ipo-current-issue) was saved outside Git and imported into the isolated local SQLite preview using `refresh_nse_ipo_feed --file`. It contained **11 issues**: eight mainboard rows with price bands and three SME rows that NSE marks `isBse=1` but without price bands. All rows have issue dates; none has lot size or allotment date. These are **NSE observations**, including the rows NSE flags as BSE listings; they are not BSE-source observations. Migrations `ipos.0012` and `ipos.0013` store each original raw row, normalized available fields, source URL, hash and observation time, plus a complete response marker. The authenticated `/api/v1/ipos/feed-watch/` endpoint reads only the latest complete saved response, including an empty response; dropped issues leave the current watch while their history stays preserved. The IPO page shows available rows under “Exchange watch” with planning unavailable. Customer requests make **zero external calls**. No row becomes a published/canonical IPO or a planner input until all required official facts are supplied and validated.

The source response was captured around `2026-09-27T23:30:00Z`. An initial local import used an earlier approximate timestamp; a second timestamped import superseded its display record while retaining both immutable copies, so the preview database has **22 observations for 11 current issues** and one latest-response batch marker. Reimporting the same file and timestamp is idempotent. The command now accepts **only** a saved response obtained with permission:

```bash
LOTNEETI_TEST_DB=/private/tmp/lotneeti-local-preview.sqlite3 \
  .venv/bin/python backend/manage.py refresh_nse_ipo_feed \
  --file /private/tmp/approved-nse-current.json \
  --observed-at '2026-09-28T10:00:00+05:30' \
  --settings=config.settings.test
```

The command makes no network request. It limits the file to 1 MB, validates the entire list before an atomic save, and leaves prior observations intact on failure. No NSE website job is scheduled. The public endpoint is undocumented and is not an authorized background feed.

The [BSE public IPO page](https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx) returned HTTP 403 in this environment, and no verified, accessible official BSE IPO JSON endpoint/schema was available. **BSE import remains blocked**; no BSE value was invented or inferred from NSE. NSE's [Terms of Use](https://www.nseindia.com/static/nse-terms-of-use), BSE's [data feed portal](https://marketdata.bseindia.com/) and [SEBI's exchange links](https://www.sebi.gov.in/Curation_Links_for_Securities_Market_Data.html) remain relevant to confirm the exact scope of the Founder-held permission and a supported feed route.
