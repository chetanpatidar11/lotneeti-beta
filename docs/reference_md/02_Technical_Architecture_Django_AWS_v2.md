# 02_Technical_Architecture_Django_AWS_v2

LotNeeti Technical Architecture

Python/Django backend with a lean AWS beta and production upgrade path

Version 2.1 • Approved Planner baseline • September 2026

# 1. Architecture Goals

- Keep business rules in a deterministic Python domain layer that is testable without Django ORM or HTTP.

- Support website and Android APK from one primary frontend codebase.

- Keep beta cost inside the founder’s AWS credits by avoiding unnecessary managed services.

- Allow production migration to managed AWS components without rewriting planner/domain logic.

- Use adapters for IPO/GMP/AI/export integrations so external providers can change independently.

# 2. Recommended Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12+, Django, Django REST Framework. |
| Planner | Pure Python domain package inside the Django repository; no ORM calls inside core selection functions. |
| Background jobs | Celery + Redis; Celery Beat for scheduled providers, recurring debits and maintenance. |
| Database | PostgreSQL. |
| Frontend | Next.js/React + TypeScript; responsive web-first. |
| Android | Capacitor wrapper over the web application for beta/public Android app; native modules only when needed. |
| Files | Amazon S3 for private exports/backups/documents. |
| Email | AWS SES for transactional email when required. |
| Observability | Django structured logs + CloudWatch/basic alarms during beta. |

# 3. Beta AWS Topology

Internet
   |
   +--> Frontend (Amplify/static deployment or Nginx-served Next.js)
   |
   +--> HTTPS / Nginx
           |
           +--> Django + DRF
           +--> Celery worker
           +--> Celery Beat
           +--> Redis
           +--> PostgreSQL
                    |
                    +--> private S3 backups / exports

For Beta 0-2, PostgreSQL, Redis, Django and Celery may share one modest EC2 instance. Do not add ALB, ECS, ElastiCache, NAT Gateway or RDS until metrics justify the recurring cost. Nightly encrypted PostgreSQL backups go to private S3.

## 3.1 Production evolution

CloudFront / WAF
      |
     ALB
      |
 ECS Fargate (Django web + Celery)
      |
 RDS PostgreSQL  +  ElastiCache Redis
      |
      S3

Migration is operational rather than architectural because PostgreSQL and the Django application remain the same logical components.

# 4. Django Modular Monolith

| Django app/package | Responsibility |
| --- | --- |
| accounts | User, workspace, membership, authentication hooks. |
| investors | Investor, PAN metadata, applicant priority, demats. |
| funding | Bank accounts, UPI handles, balances, funding preferences, recurring debits. |
| ipos | IPO master, issue facts, GMP observations, source metadata, publication state. |
| planner | Planner snapshots, policy resolution, plan runs, rows, explanations and audit. |
| applications | Submitted applications, blocks, statuses, allotments and release state. |
| portfolio | Share credits, sales, charges and realized P&L. |
| exports | Broker/template adapters and generated files. |
| integrations | IPO/GMP provider adapters, AI summarizer, notifications. |
| platform_admin | Platform policies, provider health, AI/content overrides, feature flags. |

# 5. Core Data Model

| Model | Key fields / purpose |
| --- | --- |
| Workspace | owner, settings, GMP auto-select threshold, cross-funding defaults. |
| WorkspaceMembership | user, workspace, OWNER/OPERATOR/VIEWER. |
| Investor | workspace, name, PAN encrypted/hash lookup, priority, active. |
| DematAccount | investor, depository, DP ID, client ID/BO ID, broker, active. |
| BankAccount | workspace, owner investor, bank, masked/encrypted account number, current_balance, active, cross-funding policy. |
| UPIHandle | bank account, holder investor/name, handle, verified, active, optional limit overrides. |
| FundingPreference | beneficiary investor, bank account, priority, enabled. |
| BalanceChange | bank, delta or set operation, balance_after, type, note, actor, timestamp. |
| RecurringDebit | bank, name, amount, recurrence, next_due_date, active/paused. |
| IPO | issue facts, dates, lot/price, allotment date, status, source provenance. |
| GMPObservation | IPO, provider, value, observed/fetched times, source URL/hash. |
| IPOUserDecision | workspace, IPO, DEFAULT/APPLY/SKIP, optional mode override. |
| PlanRun | workspace, planner_version, input hash/snapshot, status, generated_at. |
| PlanRow | IPO, investor, category, lots, amount, demat, bank, UPI, lock state, warnings/explanation. |
| Application | plan row link, submitted time, bank/UPI, amount, application status. |
| Allotment | application, allotted quantity/cost, result, recorded_at. |
| Sale | investor/IPO, quantity, price, charges, realized result. |

## 5.1 Sensitive field strategy

- PAN and bank account numbers are encrypted at rest at application level and displayed masked by default.

- Store normalized hashes for exact-match/duplicate lookup without exposing plaintext in query indexes.

- Never store banking passwords, UPI PINs, broker passwords, TPINs or OTP secrets.

- Use opaque public IDs/UUIDs in APIs rather than sequential internal IDs where exposure matters.

# 6. Planner Architecture

| Planner authority: Planner Algorithm v2 Specification is the implementation contract. The 120-case test matrix plus founder golden cases gate release. |
| --- |

Django ORM -> build PlannerInputSnapshot (immutable DTOs)
                   |
                   v
             Planner v2 engine
        [selection -> coverage -> sHNI -> repair -> audit]
                   |
                   v
             PlannerResult DTO
                   |
                   v
 Django transaction -> persist PlanRun + PlanRows

## 6.1 Policy resolution

Resolve settings before the planner runs. The effective cross-funding decision follows platform default → bank/account override → workspace preference → plan override → explicit locked row. Applicant Priority and Funding Preference are separate concepts.

## 6.2 Cash-at-cutoff service

available_at(cutoff) =
    current_balance
    - active_blocks_at(cutoff)
    - provisional_plan_allocations_at(cutoff)
    - recurring_debits_due_on_or_before(cutoff)
    + expected_releases_before(cutoff)

The user-facing model remains Balance / Blocked / Planned / Available. The backend can derive timeline values without exposing reconciliation/accounting concepts.

## 6.3 Determinism and concurrency

- All sort orders end with stable IDs.

- Persist planner version, policy version and input snapshot hash on every run.

- Use a database transaction when accepting/finalizing a plan and row-level locking on relevant bank/workspace records to prevent concurrent plan commits from overspending the same balance.

- The planner itself does not mutate ORM state; it only returns a proposal.

# 7. API Design

| Endpoint family | Examples |
| --- | --- |
| Auth/workspace | /api/v1/me, /workspaces, /memberships |
| Investors | /investors, /demats, /account-imports |
| Funding | /banks, /banks/{id}/balance-changes, /upis, /funding-preferences, /recurring-debits |
| IPOs | /ipos, /ipos/{id}, /ipo-decisions, /gmp-history |
| Planner | /plans/preview, /plans/{id}, /plans/{id}/rows/{row_id}, /plans/{id}/replan, /plans/{id}/finalize |
| Exports | /plans/{id}/exports, /export-formats |
| Tracking | /applications, /applications/{id}/status, /allotments |
| Portfolio | /sales, /pnl, /reports |
| Admin | /platform/providers, /platform/ipo-overrides, /platform/policies, /platform/ai-content |

# 8. Provider / Adapter Architecture

IPOProvider
  - ManualIPOProvider (beta)
  - TestFixtureIPOProvider
  - Future permitted/licensed exchange/data provider

GMPProvider
  - ManualGMPProvider (beta)
  - Future licensed/permitted GMP provider(s)

ExportAdapter
  - Generic CSV
  - Account/broker template adapter
  - Future broker-specific adapters

Production must not depend directly on undocumented website endpoints. Adapters normalize all external data into canonical models and retain source provenance/freshness.

# 9. AI Pipeline

1.  On new/updated IPO document, queue extraction/summarization job.

2.  Extract deterministic fields with parser/rules where possible; AI produces company/business/financial/risk summaries.

3.  Store generated content and prompt/model metadata once; serve cached results to all users.

4.  Allow Data Editor/Founder Admin to edit published summary while retaining original draft/history.

# 10. Authentication

- Beta end users: email OTP/magic link and/or Google sign-in; avoid paid SMS OTP during early testing.

- Founder/admin: strong password or SSO plus authenticator-app TOTP MFA.

- Mobile OTP may be added for public launch through an approved provider after India production requirements are confirmed.

# 11. Backups and Operations

- Nightly pg_dump -> compressed/encrypted -> private S3. Keep 7 daily, 4 weekly, 3 monthly during beta.

- Test restore periodically; a backup not tested is not considered valid.

- S3 exports use short-lived signed URLs; no public buckets.

- Website CSV downloads may instead use a direct authenticated attachment generated in memory (C40, 2026-10-29). Reuse the same scoped export validation, audit the exact content hash and source plan hashes, reserve successfully exported IPOs atomically, and mark responses private/no-store. This avoids requiring S3 or a signed-link navigation for the website; the existing private S3 API remains available to other clients. No persistent plaintext file is written by the server.

- AWS Budgets alerts should be configured early to protect student credits.

# 12. Testing Strategy

| Layer | Tests |
| --- | --- |
| Domain planner | 120 matrix scenarios + 15-25 founder golden historical cases. |
| Model/service | Balance changes, recurring debit generation, allotment debit/unblock, provider normalization. |
| API | Tenant isolation, permissions, validation, idempotency, concurrency. |
| Frontend | Critical flows: onboarding, plan generation/edit, balance change, export, allotment. |
| End-to-end | 17-PAN realistic plan through export and allotment/P&L. |

# 13. Deployment Sequence

1.  Local Docker Compose for PostgreSQL/Redis and deterministic fixture data.

2.  CI runs lint/type/unit/planner tests and builds frontend/backend artifacts.

3.  Beta EC2 deploy with Nginx, Django, Celery, Redis and PostgreSQL; S3 backups.

4.  Invite-only testing and metrics.

5.  If response justifies spend: buy final domain, separate database to RDS, then scale app/worker independently.

# 14. Technical Decisions to Avoid

- Do not embed planner rules in Django views or React components.

- Do not maintain balance by hidden arithmetic without a BalanceChange history.

- Do not let AI choose numeric wallet mappings.

- Do not hard-code the founder’s 20% GMP rule for all customers.

- Do not add production-grade distributed infrastructure before beta metrics justify it.

- Do not scrape or redistribute external market data without confirming permitted use.
