# 03_Security_Access_Admin_Specification_v2

LotNeeti Security, Access & Admin Specification

Security model for a solo-founder beta that can grow into public multi-tenant use

Version 2.1 • Approved Planner baseline • September 2026

# 1. Security Objectives

- Protect PAN, demat, bank and UPI data while keeping the product easy for non-technical users.

- Ensure one workspace cannot read or change another workspace’s private data.

- Keep platform administration powerful for the founder but auditable and separable into roles later.

- Prevent planner/admin automation from silently changing user-locked choices or critical source data.

- Minimize stored secrets; the product never stores broker/bank passwords, UPI PINs, TPINs or OTPs.

# 2. Role Model

| Scope | Role | Key permissions |
| --- | --- | --- |
| Workspace | Owner | All own workspace data/settings/exports, member management, deletion/export request. |
| Workspace | Operator | Manage investors, banks, plans, tracking and exports; no ownership/security/billing settings. |
| Workspace | Viewer | Read-only dashboards/reports; sensitive fields masked unless separately permitted. |
| Platform | Founder Admin | Everything needed to operate beta; full platform control. Use MFA and audit all privileged actions. |
| Platform future | Data Editor | IPO/GMP/public content and AI corrections; no private workspace financial data. |
| Platform future | Planner Admin | Global planner defaults/bank policies/feature flags; reason and audit required. |
| Platform future | Support | Search metadata and redacted diagnostics; private values masked by default. |
| Platform future | Security Admin | Lockout/MFA reset/incident tools; no business-data edits. |
| Emergency | Break-glass | Short-lived emergency elevation, MFA, reason and alerting. |

| Beta simplification: One founder login may hold Founder Admin plus Workspace Owner. Do not duplicate accounts for each future role. Permissions remain modeled separately so staff access can be split later. |
| --- |

# 3. Authentication

| User type | Beta authentication |
| --- | --- |
| End user | Email OTP/magic link and/or Google sign-in. Persistent trusted sessions to avoid repeated authentication. |
| Founder Admin | Strong password/SSO + authenticator-app TOTP MFA. SMS alone is not sufficient for platform admin. |
| Future public mobile OTP | Add after production sender/provider requirements and abuse controls are ready. |

# 4. Authorization and Tenant Isolation

- Every private object carries workspace ownership directly or through a parent relation.

- API querysets must always scope by current workspace before object lookup; do not rely only on UI hiding.

- Object-level mutations require explicit permission checks for workspace role and object ownership.

- Platform admin endpoints live under a separate permission namespace and are not implied by Workspace Owner.

- Use automated tests that attempt cross-workspace read/update/delete for every sensitive endpoint family.

# 5. Sensitive Data Protection

Founder override, 2026-10-28: all authenticated workspace members, including Viewers, may read full PAN, bank, UPI and demat details in the website. This supersedes masked/reveal-only presentation defaults below. Viewer mutations remain prohibited; workspace scoping, encryption at rest, private no-store responses, and redaction in logs/audit metadata remain required. Deleted-bank history recorded only as a masked reference cannot reconstruct the original number.

| Data | Control |
| --- | --- |
| PAN | Application-level encryption; normalized hash for duplicate/exact lookup; UI masked except when explicitly revealed by authorized user. |
| Bank account number | Encrypted; show last 4 digits by default. |
| UPI ID | Treat as sensitive contact/payment identifier; mask where appropriate in shared/viewer contexts. |
| Demat identifiers | Encrypt or restrict based on sensitivity; never expose another workspace’s values. |
| Exports | Private S3 object; short-lived signed download; authorization rechecked before generation/download. |
| Backups | Encrypted storage, private bucket, restricted IAM, retention policy and restore testing. |

# 6. Admin Site Design

Use a dedicated staff/admin surface. Django Admin may be used internally for basic master data, but high-risk workflows should use custom admin pages with validation, reason capture and audit history.

| Admin area | Capabilities |
| --- | --- |
| IPO data | Review source values, manual overrides, freshness and publication state. |
| GMP | Provider health, enable/disable, observation corrections, temporary manual override with expiry/reason. |
| AI content | View original draft/source metadata, edit published summary, retain version history. |
| Planner policies | Edit effective-dated defaults and bank overrides; preview impact; require reason. |
| Users/workspaces | Suspend/reactivate, metadata lookup, data export/delete workflow; sensitive reveal controlled. |
| Security | MFA reset flow, forced logout, incident notes, rate-limit/abuse controls. |

# 7. Planner and Cross-Funding Controls

- Cross-funding is configurable rather than globally forbidden: platform default, bank override, workspace preference, plan override and explicit locked row.

- Same-name mapping is a strong preference, not a hidden hard block.

- Cross-funded rows display a clear warning and explanation.

- Bank-owner protection is calculated by the planner; manual locked rows are preserved but may receive blocking warnings.

- A locked infeasible row stays visible; export/finalization is blocked until user resolves or explicitly changes it.

# 8. Balance and Financial Integrity

- User sees simple +, -, Set Balance actions. Every action writes a small immutable history record containing old/new or delta, actor and timestamp.

- IPO blocks do not directly reduce Balance; they reduce Available.

- Allotment recording is the single user event that deducts actual allotted cost and releases the application block.

- Recurring debit execution is idempotent: the same due occurrence cannot be posted twice.

- Plan finalization and application status transitions use database transactions to prevent double-spend state.

# 9. Audit Events

| Event class | Examples |
| --- | --- |
| Authentication | Admin login, MFA reset, failed login threshold, session revoke. |
| Sensitive data | PAN/bank reveal, export generation/download, account import. |
| Planner | Plan run, locked-row change, policy override, finalization, export. |
| Financial | Balance + / - / Set, recurring debit execution, allotment debit/unblock, sale entry. |
| Admin content | IPO override, GMP override/source disable, AI summary edit, planner default change. |
| Access | Member invitation/role change, workspace suspension, user deletion/export request. |

# 10. Web/API Security Baseline

- HTTPS only; secure/HttpOnly/SameSite cookies or equivalent token storage pattern.

- CSRF protection for cookie-authenticated mutations, strict CORS, security headers and input validation.

- Rate limits on login/OTP, imports, exports, expensive planner runs and admin endpoints.

- Malware/content-type validation for uploads; never execute uploaded spreadsheets/documents.

- Parameterized ORM queries; no raw SQL from user input.

- Secrets in AWS environment/secret storage, never in Git repository or frontend bundles.

# 11. Privacy and User Controls

- Explain why PAN/demat/bank data is required at collection time.

- Allow workspace data export and deletion request workflows before public launch.

- Collect only fields needed for planning/tracking; do not ask for bank credentials.

- Use masked defaults and explicit reveal actions for sensitive values.

- Publish privacy policy and terms before public beta beyond invited testers.

# 12. Incident and Recovery

1.  Detect unusual access/provider/admin activity through logs and alerts.

2.  Contain by disabling account/provider, rotating credentials or revoking sessions.

3.  Preserve audit evidence and determine affected workspaces/data.

4.  Recover from verified backups and test critical planner/balance invariants.

5.  Communicate appropriately based on impact and legal obligations.

# 13. Public Launch Security Gate

| Control | Required before public launch |
| --- | --- |
| Admin MFA | Yes |
| Tenant isolation tests | Yes |
| Encrypted sensitive fields | Yes |
| Private tested backups | Yes |
| Data export/delete workflow | Yes |
| Privacy/Terms | Yes |
| Audit trail | Yes |
| Rate limiting | Yes |
| Permitted production data feeds | Yes |
| Support/incident email and procedure | Yes |
