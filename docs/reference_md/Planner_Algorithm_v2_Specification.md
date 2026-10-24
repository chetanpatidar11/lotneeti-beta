# Planner_Algorithm_v2_Specification

LotNeeti Planner Algorithm v2

Functional and deterministic planning specification

Draft for implementation review • Version 2.0

# Document purpose

This document freezes the planner behavior agreed for the fresh LotNeeti website + Android beta. It preserves the proven numeric limits and cash/UPI ideas from the previous planner while simplifying the model for non-technical users and making every generated application editable before export.

| Design principle: Automation proposes a complete plan; the user can select/unselect IPOs, change category, bank, UPI, demat or lots, then lock the final row. The planner must explain conflicts instead of silently undoing user choices. |
| --- |

# 1. Source basis and v2 changes

The legacy planner already established useful behavior: one-PAN-per-IPO eligibility, 1-lot retail, minimum whole-lot sHNI above ₹2,00,000, rolling UPI/bank limits, future cash reuse, cross-name funding, locked rows, deterministic tie-breaking and a final safety audit. Planner v2 keeps those foundations but changes the decision hierarchy.

| Legacy concept | Planner v2 decision |
| --- | --- |
| Tax rank | Removed. Replaced by direct applicant priority 1, 2, 3, ... |
| GMP floor as hard eligibility | Becomes a user-configurable auto-selection rule. User may manually APPLY or SKIP any IPO. |
| Own wallet hard precedence | Becomes strong preference. Cross-funding remains allowed when enabled. |
| Round-robin between same-cutoff IPOs | Replaced by higher-GMP-first priority when selected IPOs compete for scarce resources. |
| Balance accounting/reconciliation concepts | User sees only Balance, Blocked, Planned and Available; balance changes use +, -, or Set Balance. |
| Tax-oriented sHNI seeding | Applicant priority + IPO strategy + same-name preference + feasibility. |

# 2. Frozen business defaults

| Decision | Planner v2 rule |
| --- | --- |
| Retail quote | Exactly 1 lot by default. |
| sHNI threshold | Strictly more than ₹2,00,000. |
| Automatic sHNI quote | Smallest whole-lot amount strictly above ₹2,00,000. Do not top up merely because more cash exists. |
| Rolling window | 24 hours. |
| UPI application cap | 6 non-cancelled applications inside the rolling window. |
| Bank application cap | 6 non-cancelled applications inside the rolling window; shared across UPIs mapped to that bank when bank-level enforcement is enabled. |
| UPI amount cap | ₹5,00,000 inside the rolling window. |
| Bank amount cap | ₹5,00,000 inside the rolling window. |
| Retail application time | Default 5:00 PM on closing date; admin-configurable. |
| sHNI application time | Default 4:00 PM on closing date; admin-configurable. |
| Manual record plan after closing | Explicitly select a closed, allotment or listed IPO to generate/review/save and record submission details at any time. Closed IPOs are never automatically selected. Exchange status and cutoffs are unchanged; late plans cannot be exported for new bids. |
| Expected cash reuse after IPO | From the next calendar day after the IPO allotment date. |
| User personal GMP default | 20% auto-selection threshold for the founder workspace; not a platform-wide mandatory rule. |

# 3. User-facing money model

The planner backend may keep transaction history, but users should not need accounting terminology. Every bank account exposes only four operational numbers.

| Number | Meaning |
| --- | --- |
| Balance | The amount the user says is currently in the bank. |
| Blocked | Amount currently tied up in IPO mandates/applications. |
| Planned | Amount reserved by the current plan but not yet applied/blocked. |
| Available | Cash usable for another application at the relevant time. |

Available now = max(0, Balance - Blocked - Planned)

For a future application cutoff, the planner also subtracts recurring debits scheduled on or before that cutoff and applies expected unblocks that occur before that cutoff.

## 3.1 Manual balance controls

- + Add Money: increases current balance by the entered amount.

- - Remove Money: decreases current balance by the entered amount.

- Set Balance: replaces current balance with the entered exact amount.

- Every operation stores a small history entry so accidental changes can be understood or reversed by another balance operation.

## 3.2 Allotment handling

| Outcome | Effect |
| --- | --- |
| Not allotted | Remove the application block. Balance does not change. |
| Allotted | Deduct actual allotted cost from Balance and remove the full application block. |
| Partial allotment | Deduct actual allotted cost and release the rest of the blocked application amount. |

| Simple rule: Recording allotment is the event that performs debit/unblock. There is no separate reconciliation workflow. |
| --- |

## 3.3 Recurring debits (EMIs and similar)

Users may create recurring scheduled debits from the bank screen. Example fields: Bank, Name, Amount, Frequency, Day/Date, Start Date, optional End Date, Active/Paused.

Future available at cutoff = current balance - active blocks - planned allocations - scheduled debits before cutoff + expected releases before cutoff

When the scheduled date arrives, the recurring debit automatically creates a normal negative balance change. The user sees the new balance immediately.

# 4. Core entities used by the planner

| Entity | Minimum planner fields |
| --- | --- |
| IPO | price band, upper price, lot size, open/close dates, allotment date, GMP %, status, selected state, application mode |
| Applicant | PAN, active, demat, planning priority, retail/sHNI preference if any |
| Demat | applicant, DP type, DP ID/client ID, active |
| Bank account | owner, current balance, active, cross-funding policy, restricted applicant if any |
| UPI | bank account, holder, active, verified, per-UPI limit overrides if any |
| Funding preference | beneficiary applicant, preferred funding bank, priority order, enabled |
| Recurring debit | bank, amount, schedule, active/paused |
| Existing application/block | IPO, applicant, bank/UPI, amount, status, submitted time, expected release date |
| Plan row | IPO, applicant, category, lots, amount, demat, bank, UPI, locked flag, warnings, explanation |

# 5. IPO selection and priority

GMP is a draft-selection input, not a hard platform decision. Each workspace has an auto-select threshold. For the founder workspace the initial value is 20%.

if user_decision == APPLY:
    selected = True
elif user_decision == SKIP:
    selected = False
else:
    selected = gmp_percent >= workspace.auto_select_gmp_percent

- A user may manually select an IPO below the threshold.

- A user may manually unselect an IPO above the threshold.

- A manual decision persists when GMP changes until the user chooses “Reset to automatic”.

- The planner receives only the final selected IPO set.

## 5.1 Selected IPO ordering

When selected IPOs compete for the same cash or rolling-limit capacity, higher GMP receives priority. This is the chosen behavior over equal spreading.

1.  Sort selected IPOs by current GMP percentage descending.

2.  If GMP is equal, earlier application cutoff comes first.

3.  If still equal, use stable IPO ID ascending so repeated runs remain deterministic.

| Important: The 20% threshold is only a personal default. The higher-GMP-first ordering applies to the final selected list, including manually selected below-threshold IPOs. |
| --- |

# 6. Applicant priority

Tax ranking is removed completely. Every applicant may have a direct planning priority such as 1, 2, 3, 4, 5. Lower number means higher priority.

- Priority is used whenever there is not enough cash/UPI capacity to cover all applicants.

- Priority is used when deciding who receives scarce sHNI opportunities.

- Priority is shared by Retail and sHNI; there is no separate tax model.

- Equal priority is resolved by stable applicant ID.

# 7. Category rules

| Hard invariant: For one IPO, one PAN can have at most one application. That application is either Retail or sHNI, never both. |
| --- |

| Mode | Behavior |
| --- | --- |
| Retail Only | All automatic rows are 1-lot Retail. No automatic sHNI upgrade. |
| Retail + sHNI | Build Retail coverage first, then allow sHNI upgrades where the user/planner chooses and cash permits. |
| sHNI Preferred | After baseline coverage, upgrade as many eligible PANs as possible to the minimum valid sHNI quote. |
| Custom | User decides category/lots applicant-by-applicant; planner maps and validates funding. |

## 7.1 sHNI Preferred means “maximum count”, not maximum spend

The automatic objective is to maximize the number of minimum-valid sHNI applications. It must not add extra lots merely to consume leftover cash.

min_sHNI_lots = floor(200000 / one_lot_amount) + 1
min_sHNI_amount = min_sHNI_lots * one_lot_amount

# 8. Cross-funding policy

Cross-funding remains supported for both Retail and sHNI. Same-name/own mapping is a strong preference, not a universal hard restriction.

| Policy layer | Purpose |
| --- | --- |
| Platform default | Base behavior for all workspaces. |
| Bank/account override | Disable or warn for a bank where cross-funding should not be used. |
| Workspace preference | Workspace-wide allow/disable/default behavior. |
| Plan override | Temporary decision for one planning session/IPO set. |
| Manual locked row | User may retain an explicitly chosen mapping; validation still shows warnings/errors. |

# 9. Preferred cross-funding banks

A beneficiary applicant may have an ordered list of preferred funding banks. This is separate from Applicant Priority.

Mother funding preference:
1. Her own feasible wallet
2. Wife HDFC (priority 1)
3. Chetan SBI (priority 2)
4. Father ICICI (priority 3)
5. Other allowed wallets

Funding preference answers “which bank should fund this PAN?” while applicant priority answers “which PAN should receive scarce capacity first?”

# 10. Protect bank owner before cross-funding

Before a bank is used to fund another applicant, the planner protects the owner’s own baseline applications across selected overlapping IPOs that need the same cash window.

cross_fundable_cash_at_time =
    available_cash_at_time
    - owner_required_baseline_cash_at_time
    - protected_scheduled_debits_at_time

| Example | Result |
| --- | --- |
| Wife balance ₹50,000; one ₹15,000 IPO | Reserve ₹15k for wife. Up to ₹35k may cross-fund mother; both can use wife bank. |
| Wife balance ₹50,000; two overlapping ₹15,000 IPOs | Reserve ₹30k for wife. Remaining ₹20k can cross-fund mother for one IPO; mother uses another active bank for the second. |
| Wife balance ₹50,000; three overlapping ₹15,000 IPOs | Reserve ₹45k for wife. ₹5k remains; mother must use another bank for all three unless cash is released between cutoffs. |

| Coverage rule: Owner protection is a preference guard, not permission to create impossible rows. If preserving every owner ticket makes coverage impossible, the planner may use allowed cross-funding according to overall coverage and user priority, but it must explain the trade-off. |
| --- |

# 11. Wallet feasibility (hard checks)

A wallet is a bank-account + UPI combination. A candidate may be ranked only after it passes every applicable hard check.

1.  Applicant is active and has an active demat for the IPO.

2.  Applicant does not already have a non-cancelled application for the same IPO.

3.  Bank is active.

4.  UPI is active and verified.

5.  Bank policy permits this applicant (including same-PAN-only restrictions where configured).

6.  Effective cross-funding policy allows the mapping when names/ownership differ.

7.  Available cash at the application cutoff is at least the full quote amount.

8.  UPI rolling application count and amount caps have room.

9.  Bank rolling application count and amount caps have room.

10.  The candidate does not double-spend cash already needed by earlier selected/locked rows at the same time.

# 12. Rolling limits

The 24-hour rolling tracker counts non-cancelled submitted applications inside the half-open window (cutoff - 24 hours, cutoff]. Release of funds does not erase the submitted application from the rolling count while it remains inside that time window.

- Default maximum 6 applications per UPI and 6 per bank account.

- Default maximum ₹5,00,000 submitted amount per UPI and per bank account.

- If one bank has multiple UPIs, bank-level enforcement aggregates all of them.

- Cancelled applications do not consume the rolling slot/amount.

# 13. Cash timeline and expected release

The planner evaluates cash at the application cutoff, not only at the present moment. Blocked cash is reusable only after its expected release boundary.

- Planning assumption: IPO funds become reusable from the next calendar day after the allotment date.

- If an application cutoff is on the allotment date itself, that cash remains unavailable.

- If the cutoff is on the next day, the cash may be reused in planning.

- When actual allotment is recorded, real debit/unblock state replaces the expected planning assumption.

# 14. Planner execution phases

1.  Build immutable input snapshot: IPOs, final selection states, GMP, applicants, priorities, wallets, current balances, blocks, recurring debits, limits, manual locks and settings.

2.  Calculate quote sizes and future cash timelines.

3.  Apply and validate locked/manual rows first; never silently move them.

4.  Sort selected IPOs by GMP descending (then cutoff, then ID).

5.  Baseline coverage phase: for each selected IPO in that order, try to give every eligible applicant one 1-lot Retail row unless the applicant/category is explicitly fixed to sHNI or Custom.

6.  When baseline resources are scarce, use Applicant Priority (lower number first) within that IPO.

7.  Continue through lower-GMP selected IPOs with remaining/reusable resources.

8.  sHNI phase: process selected IPOs again by GMP descending. For Retail + sHNI or sHNI Preferred, attempt Retail→sHNI upgrades without creating a second row for the same PAN.

9.  In sHNI Preferred mode, continue upgrades until no more feasible minimum-sHNI conversions exist.

10.  Run a bounded repair/rehome pass where moving unlocked Retail rows can safely free a better wallet for sHNI; rollback the entire local change if every displaced row cannot be re-homed.

11.  Run same-size owner-affinity cleanup swaps only when they improve own/same-name mapping and do not change cash/limit totals.

12.  Run the independent final audit from scratch.

13.  Persist the proposed plan with explanations, warnings, planner version and input snapshot hash.

# 15. Retail wallet ranking

After hard checks, candidate selection should use ordered preferences rather than one opaque weighted score wherever possible.

1.  Honor an explicit locked/manual bank+UPI choice.

2.  Prefer own/same-name feasible wallet.

3.  If cross-funding is needed, prefer the beneficiary’s configured Funding Preference order.

4.  Protect the bank owner’s baseline needs across overlapping selected IPOs.

5.  Prefer cash that is useful for Retail but cannot support minimum sHNI (stranded small cash).

6.  Prefer better rolling-limit headroom.

7.  Prefer tighter sufficient balance when all stronger rules are equal.

8.  Stable bank ID, then UPI ID as deterministic final tie-breakers.

# 16. sHNI wallet ranking

1.  Honor explicit locked/manual choice.

2.  Use Applicant Priority to decide which PAN is offered scarce sHNI capacity first.

3.  Prefer own/same-name feasible wallet for that applicant.

4.  If own wallet is not feasible, use configured preferred cross-funding banks when cross-funding is allowed.

5.  Protect owner baseline needs for any cross-funded bank.

6.  Prefer the smallest leftover balance after the minimum sHNI quote.

7.  Prefer better rolling-limit headroom.

8.  Stable bank ID, then UPI ID.

# 17. Manual edits and row locks

Every generated row is editable before export. User changes trigger immediate validation but do not get silently reverted.

| Editable field | Behavior after edit |
| --- | --- |
| Applicant | Revalidate duplicate PAN, eligibility and demat. |
| Category | Recalculate lots/amount and enforce Retail OR sHNI exclusivity. |
| Lots | Recalculate amount and rolling-limit/cash impact. |
| Demat | Validate ownership/active state. |
| Bank | Recalculate available cash, owner protection and policy. |
| UPI | Validate bank mapping, active/verified state, limits and cross-funding warning. |
| Lock | Locked row becomes a hard user instruction for subsequent re-plans. |

| Locked infeasible row: Keep the row visible and mark it BLOCKING. Do not silently delete or remap it. |
| --- |

# 18. Warning and error model

| Code | User-facing meaning | Severity |
| --- | --- | --- |
| UNCOVERED_PAN | No usable funding source was available for this PAN. | Info |
| INSUFFICIENT_BALANCE | This bank does not have enough available money for the row. | Blocking |
| UPI_LIMIT_EXCEEDED | This UPI has reached the configured rolling limit. | Blocking |
| BANK_LIMIT_EXCEEDED | This bank account has reached the configured rolling limit. | Blocking |
| INVALID_UPI | UPI is inactive/unverified or not usable. | Blocking |
| BANK_PAN_RESTRICTED | This bank is restricted to another applicant. | Blocking |
| CROSS_FUNDING | Another person’s funding source is being used. | Warning |
| OWNER_CASH_CONFLICT | This cross-funded row uses money protected for the bank owner’s own selected IPO. | Warning/Blocking by policy |
| FUTURE_CASH_CONFLICT | The mapping may consume cash needed before it is expected to be released. | Warning/Blocking by policy |
| LOCKED_ROW_INFEASIBLE | A locked user instruction cannot currently be executed. | Blocking |

# 19. Explainability output

Every automatic row should carry a short ordered reason list. The UI can translate these into simple sentences.

Applicant: Mother
IPO: ABC Ltd
Category: RETAIL
Bank: Wife HDFC
Amount: ₹15,000
Reasons:
- Applicant priority 4
- Own wallet unavailable
- Wife HDFC is cross-funding priority 1
- Wife's own selected IPO cash remains protected
- Bank and UPI rolling limits have room
Warning: Cross-funded

# 20. Determinism and versioning

- Same input snapshot + same settings + same planner version must produce the same plan.

- Every ordering ends with stable IDs as tie-breakers.

- Planner run stores planner_version, settings_version, input_snapshot_hash and output_hash.

- Changing source order from the database must not change the result.

- Old plans remain explainable after future algorithm updates.

# 21. Independent final audit

The final audit must not trust the optimizer’s internal counters. It replays the entire proposed plan from the frozen snapshot and verifies:

- No PAN has two rows for the same IPO.

- Retail and sHNI do not coexist for the same PAN/IPO.

- No bank cash is double-spent at overlapping times.

- Expected releases are only used on or after the next calendar day after allotment.

- Recurring debits before cutoffs are included.

- UPI and bank 24-hour count/amount limits are respected.

- All locked rows are preserved exactly and any infeasibility is visible.

- Planned amount totals equal the sum of plan rows.

# 22. Planner v2 pseudocode

snapshot = build_snapshot()
selected_ipos = resolve_user_selection(snapshot.ipos, workspace.gmp_threshold)
selected_ipos.sort(key=(-gmp_percent, cutoff_time, ipo_id))

apply_locked_rows(snapshot)

# Phase 1: baseline PAN coverage
for ipo in selected_ipos:
    for applicant in eligible_applicants(ipo, order=(priority, applicant_id)):
        if already_has_row(applicant, ipo):
            continue
        category = fixed_category_or_retail(applicant, ipo)
        quote = quote_for(category, ipo)
        wallet = best_wallet(applicant, ipo, quote, protect_owner=True)
        if wallet:
            place_row(applicant, ipo, category, quote, wallet)
        else:
            record_uncovered(applicant, ipo)

# Phase 2: sHNI upgrades
for ipo in selected_ipos:
    if ipo.mode not in {RETAIL_PLUS_SHNI, SHNI_PREFERRED}:
        continue
    for applicant in eligible_upgrade_candidates(ipo, order=(priority, applicant_id)):
        try_upgrade_retail_to_min_shni(applicant, ipo)
        if ipo.mode == SHNI_PREFERRED:
            continue until no more feasible upgrades exist

repair_and_rehome_bounded()
owner_affinity_cleanup()
final_audit_from_scratch()
persist_plan_with_explanations()

# 23. End-to-end worked examples

## 23.1 Wife / mother preferred cross-funding

Retail quote ₹15,000. Wife balance ₹50,000. Mother has ₹0. Mother’s cross-funding priority 1 is Wife HDFC.

| Selected overlapping IPOs | Wife own reserve | Cross-fundable surplus | Expected mapping |
| --- | --- | --- | --- |
| 1 | ₹15,000 | ₹35,000 | Wife + Mother may both use Wife HDFC. |
| 2 | ₹30,000 | ₹20,000 | Wife uses HDFC for both. Mother uses HDFC for one and another eligible bank for the other. |
| 3 | ₹45,000 | ₹5,000 | Wife uses HDFC for all three. Mother uses other eligible banks. |

## 23.2 Higher GMP IPO first

Two selected IPOs overlap. IPO A GMP 35%; IPO B GMP 22%. 17 PANs exist but current resources allow only 20 Retail applications.

- Planner first attempts all 17 PANs in IPO A, using applicant priority when resources are tight.

- Remaining capacity is used for IPO B, so about 3 additional PANs may be covered there.

- The planner does not equal-spread 10/10 because higher GMP priority was explicitly chosen.

## 23.3 sHNI Preferred

10 PANs, Retail ₹15,000, minimum sHNI ₹2,10,000, usable capital ₹8,85,000.

Baseline retail = 10 × ₹15,000 = ₹1,50,000
Extra required per Retail→sHNI upgrade = ₹1,95,000
Remaining after baseline = ₹7,35,000
Maximum upgrades = floor(₹7,35,000 / ₹1,95,000) = 3

Result: 3 sHNI + 7 Retail, assuming wallet/rolling-limit feasibility. Do not top up those three sHNI rows with the remaining cash.

## 23.4 Recurring EMI before cutoff

Current balance ₹2,50,000
EMI on 5 Oct: -₹20,000
IPO cutoff 6 Oct
Planner cash at cutoff before IPO blocks: ₹2,30,000

# 24. Explicit non-goals for v2

- No automatic broker login, OTP handling or IPO submission.

- No bank statement reconciliation workflow.

- No tax classification/ranking logic.

- No requirement to spend every available rupee.

- No hidden AI decision inside wallet selection; numeric planner logic is deterministic.

- No permanent rule that all users must apply when GMP is 20% or higher; selection belongs to the user/workspace.

# 25. Implementation acceptance criteria

- All P0 tests in the companion test matrix pass.

- Golden historical scenarios from the founder’s real 17-PAN workflow match the agreed expected plans or have documented intentional differences.

- Repeated identical runs are byte-for-byte stable at the logical plan level.

- Every generated row has a human-readable reason and all blocking conflicts are visible before export.

- A user can change bank/UPI/demat/category/lots and lock the row without losing the edit on re-plan.
