# Planner_v2_Test_Matrix

LotNeeti Planner v2 Test Matrix

Functional, edge-case and regression scenarios

Draft for implementation review • Version 2.0

# How to use this matrix

Implement these as automated domain/service tests before relying on the planner for real IPO operations. P0 tests block beta release. P1 tests should pass before invitation beta. P2 tests cover robustness, usability and future regression protection.

| Golden tests: In addition to the generic cases below, create 15–25 historical snapshots from the founder’s actual 17-PAN workflow and freeze the agreed expected output for each one. |
| --- |

# Coverage summary

| Test group | Cases |
| --- | --- |
| Applicant Priority | 4 |
| Audit & Determinism | 7 |
| Balance | 7 |
| Blocks & Allotment | 6 |
| Eligibility | 8 |
| End-to-End | 6 |
| Funding Preference | 6 |
| IPO Selection | 9 |
| Locked & Manual | 8 |
| Multi-IPO | 8 |
| Own/Cross Funding | 7 |
| Owner Protection | 6 |
| Quote & Category | 8 |
| Recurring Debit | 6 |
| Repair & Rehome | 5 |
| Retail Wallet | 4 |
| Rolling Limits | 7 |
| sHNI | 8 |

Total defined cases: 120

# Quote & Category

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| QC-001 | Retail quote is one lot | Upper price ₹100, lot 150 | Retail amount = ₹15,000; lots = 1. | P0 |
| QC-002 | Minimum sHNI exact math | One lot ₹15,000 | floor(₹2L/₹15k)+1 = 14 lots = ₹2.10L. | P0 |
| QC-003 | sHNI when one lot already above ₹2L | One lot ₹2.25L | Minimum sHNI = 1 lot = ₹2.25L. | P0 |
| QC-004 | Do not top up automatic sHNI | Minimum valid sHNI ₹2.10L; bank has ₹5L | Automatic row remains ₹2.10L unless user changes lots. | P0 |
| QC-005 | Retail/sHNI exclusivity | Same PAN/IPO has existing Retail row | Planner cannot create second sHNI row; upgrade replaces category. | P0 |
| QC-006 | Retail Only mode | IPO set Retail Only; ample funds | All automatic rows remain Retail. | P0 |
| QC-007 | sHNI Preferred max-count | 10 PAN; example capital permits 3 upgrades | Result 3 minimum sHNI + 7 Retail if wallets feasible. | P0 |
| QC-008 | Custom category preserved | User fixes PAN A to sHNI and PAN B Retail | Planner keeps those categories and only maps funding. | P0 |

# IPO Selection

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| IS-001 | Auto-select above threshold | Threshold 20%; GMP 25%; user decision DEFAULT | Selected. | P0 |
| IS-002 | Auto-unselected below threshold | Threshold 20%; GMP 12%; DEFAULT | Not selected. | P0 |
| IS-003 | Manual APPLY below threshold | GMP 8%; user decision APPLY | Selected. | P0 |
| IS-004 | Manual SKIP above threshold | GMP 35%; user decision SKIP | Not selected. | P0 |
| IS-005 | Manual SKIP persists after GMP rises | User SKIP at 25%; GMP later 40% | Still not selected. | P0 |
| IS-006 | Reset to automatic | Previously SKIP; reset; GMP 30% | Selected by auto rule. | P0 |
| IS-007 | Higher GMP ordering | A 35%, B 22%, both selected | A planned before B. | P0 |
| IS-008 | Equal GMP tie | A/B both 25%; A cutoff earlier | A planned first. | P0 |
| IS-009 | Equal GMP/cutoff deterministic tie | Same GMP and cutoff | Lower stable IPO ID planned first. | P0 |

# Eligibility

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| EL-001 | Inactive applicant | Applicant inactive | No automatic row. | P0 |
| EL-002 | Missing demat | Applicant active, no active demat | No automatic row; uncovered reason. | P0 |
| EL-003 | Already applied same IPO | Existing non-cancelled application | No new row for same PAN/IPO. | P0 |
| EL-004 | Cancelled prior application | Prior application cancelled | Applicant can be planned again. | P0 |
| EL-005 | Inactive bank | Only bank inactive | Bank excluded. | P0 |
| EL-006 | Inactive UPI | Only UPI inactive | Wallet excluded. | P0 |
| EL-007 | Unverified UPI | UPI active but unverified | Wallet excluded. | P0 |
| EL-008 | Restricted bank wrong applicant | Bank restricted to A; planning B | Wallet excluded. | P0 |

# Applicant Priority

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| AP-001 | Priority decides scarce Retail | Two PANs compete for one ₹15k slot; priorities 1 and 2 | Priority 1 gets coverage. | P0 |
| AP-002 | Priority decides scarce sHNI | Two feasible PANs, one sHNI opportunity; priorities 2 and 5 | Priority 2 upgraded first. | P0 |
| AP-003 | Equal priority deterministic tie | Same priority and feasibility | Lower applicant ID first. | P0 |
| AP-004 | Priority applies to cross-funded candidate | Higher-priority PAN only has cross-funded wallet; lower-priority has own wallet | Higher-priority PAN is considered first; wallet preference is evaluated within that PAN. | P0 |

# Balance

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| BA-001 | Add money | Balance ₹50k; +₹5k | Balance becomes ₹55k. | P0 |
| BA-002 | Remove money | Balance ₹50k; -₹5k | Balance becomes ₹45k. | P0 |
| BA-003 | Set balance | Balance ₹50k; Set ₹61,380 | Balance becomes ₹61,380. | P0 |
| BA-004 | Blocked does not reduce Balance | Balance ₹50k; block ₹15k | Balance ₹50k, Blocked ₹15k, Available ₹35k. | P0 |
| BA-005 | Planned reduces Available | Balance ₹50k; Planned ₹15k | Balance ₹50k, Available ₹35k. | P0 |
| BA-006 | No negative available | Balance ₹10k; block/planned ₹15k due to locked row | Available shown/calculated as 0; row blocking error. | P0 |
| BA-007 | Manual add after plan | Plan uses ₹15k of ₹20k; user adds ₹10k | Revalidation sees ₹30k balance and new available amount. | P0 |

# Recurring Debit

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| RD-001 | EMI before cutoff reduces future cash | Balance ₹2.5L; EMI ₹20k on 5th; cutoff 6th | Planner sees ₹2.3L before IPO allocations. | P0 |
| RD-002 | EMI after cutoff ignored for that cutoff | Same EMI 7th; cutoff 6th | Planner sees ₹2.5L for 6th. | P0 |
| RD-003 | Monthly EMI posts on due date | ₹8.5k recurring monthly | Automatic -₹8.5k balance transaction on due date. | P0 |
| RD-004 | Paused EMI | Recurring debit paused before due date | No deduction and no future reserve while paused. | P0 |
| RD-005 | Edited EMI amount | ₹8.5k changed to ₹9k before due date | Future planning uses ₹9k and due transaction is -₹9k. | P0 |
| RD-006 | Multiple recurring debits | Two debits before same cutoff | Both reduce future available cash. | P0 |

# Blocks & Allotment

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| BL-001 | Not allotted releases full block | Balance ₹50k; block ₹15k; NOT_ALLOTTED | Balance unchanged; Blocked reduces by ₹15k. | P0 |
| BL-002 | Full allotment debit | Balance ₹50k; block ₹15k; actual cost ₹14,850 | Balance ₹35,150; block removed. | P0 |
| BL-003 | Partial sHNI allotment | Block ₹2.10L; actual cost ₹42k | Deduct ₹42k; release full block record; remainder free. | P0 |
| BL-004 | Expected next-day reuse | Allotment 28 Sep; later cutoff 29 Sep | Planner may reuse expected released cash on 29 Sep. | P0 |
| BL-005 | No same-day reuse | Allotment 28 Sep; cutoff 28 Sep 5 PM | Earlier block still considered unavailable. | P0 |
| BL-006 | Actual allotment supersedes expectation | Expected release tomorrow but actual recorded today | Actual debit/unblock state governs current availability. | P0 |

# Rolling Limits

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| RL-001 | UPI count 5/6 | 5 applications in rolling window | One more application allowed. | P0 |
| RL-002 | UPI count 6/6 | 6 applications | No further row using UPI. | P0 |
| RL-003 | Explicit UPI aggregate amount cap | Override configured to ₹5L; ₹4.90L used; new quote ₹15k | Rejected. Without an explicit cap, aggregate rupee usage alone does not reject separate bids. | P0 |
| RL-004 | Bank shared cap across UPIs | Two UPIs same bank total 6 apps | Neither UPI can create another row if bank-level enforcement on. | P0 |
| RL-005 | Cancelled app does not count | 6 records but one cancelled | One slot remains. | P0 |
| RL-006 | Released app still counts inside 24h | Released funds but submitted within window | Still consumes rolling count/amount. | P0 |
| RL-007 | Application falls out of 24h window | Old application timestamp <= cutoff-24h | No longer counts under half-open rule. | P0 |

# Own/Cross Funding

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| CF-001 | Own wallet preferred Retail | Own and cross wallet both feasible | Own/same-name wallet selected unless stronger locked/funding rule says otherwise. | P0 |
| CF-002 | Own wallet preferred sHNI | Own and cross wallet both feasible | Own/same-name wallet preferred. | P0 |
| CF-003 | Cross fallback Retail | No own feasible wallet; cross enabled | Allowed cross wallet may fund. | P0 |
| CF-004 | Cross fallback sHNI | No own feasible wallet; cross enabled | Allowed cross wallet may fund minimum sHNI. | P0 |
| CF-005 | Cross disabled workspace | Only cross wallet feasible; cross disabled | No automatic assignment from cross wallet. | P0 |
| CF-006 | Bank-level cross disabled | Workspace allows cross; chosen bank disallows | Bank excluded for cross funding. | P0 |
| CF-007 | Cross warning emitted | Cross mapping selected | Plan row includes CROSS_FUNDING warning/explanation. | P0 |

# Funding Preference

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| FP-001 | Preferred cross bank wins | Mother has no own wallet; Wife HDFC priority 1, Chetan SBI priority 2, both feasible | Wife HDFC selected. | P0 |
| FP-002 | Priority-1 bank insufficient | Wife HDFC cannot fund; Chetan SBI can | Use priority-2 bank. | P0 |
| FP-003 | Priority-1 bank limit exhausted | Wife HDFC rolling cap full; SBI feasible | Use SBI. | P0 |
| FP-004 | Preferred bank disabled | Priority-1 preference disabled | Skip to next enabled preference. | P0 |
| FP-005 | Own wallet beats funding preference | Mother own wallet feasible and Wife HDFC preferred cross exists | Own wallet preferred. | P0 |
| FP-006 | No configured preference | Only cross wallets available | Fall back to general allowed cross-wallet ranking. | P0 |

# Owner Protection

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| OP-001 | Wife/mother one IPO | Wife ₹50k; one ₹15k IPO; mother ₹0 | Reserve wife ₹15k; both can use wife bank. | P0 |
| OP-002 | Wife/mother two overlapping IPOs | Wife ₹50k; two × ₹15k; mother ₹0 | Reserve wife ₹30k; wife bank can fund mother for only one IPO. | P0 |
| OP-003 | Wife/mother three overlapping IPOs | Wife ₹50k; three × ₹15k | Reserve wife ₹45k; mother cannot use wife bank for a ₹15k row. | P0 |
| OP-004 | Release between IPOs changes reserve | Earlier block expected to release before later cutoff | Released cash can support later owner/cross rows. | P0 |
| OP-005 | Scheduled EMI reduces cross-fundable surplus | Wife ₹50k, owner reserve ₹30k, EMI ₹10k before cutoff | Only ₹10k cross-fundable; cannot fund ₹15k mother row. | P0 |
| OP-006 | Other safe cross bank exists | Owner bank unsafe for mother, alternative neutral bank feasible | Use safe alternative. | P0 |

# Retail Wallet

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| RW-001 | Stranded small balance preferred | Own/policy equal; bank A ₹30k, bank B ₹2.10L; Retail ₹15k | Prefer ₹30k bank to preserve sHNI-capable bank. | P0 |
| RW-002 | Better limit headroom | Comparable wallets; one has 1 slot left, other 5 | Prefer wallet with more headroom after stronger rules. | P0 |
| RW-003 | Tighter sufficient balance tie-break | Comparable ₹30k vs ₹60k for ₹15k | Prefer ₹30k. | P0 |
| RW-004 | Stable bank/UPI tie-break | All ranking factors equal | Lower bank ID then lower UPI ID. | P0 |

# sHNI

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| SH-001 | Same-name sHNI preference | Own and cross feasible | Use own/same-name wallet. | P0 |
| SH-002 | Cross-funded sHNI allowed | Own insufficient; preferred cross bank feasible | Use cross-funded bank if policy allows. | P0 |
| SH-003 | Tightest sufficient sHNI balance | Two otherwise equal banks ₹2.52L and ₹3.40L; quote ₹2.04L | Prefer ₹2.52L. | P0 |
| SH-004 | sHNI upgrade preserves row count | Retail row upgraded | Exactly one row remains for PAN/IPO, now sHNI. | P0 |
| SH-005 | sHNI not possible due limits | Cash enough but UPI/bank cap exhausted | Keep Retail if feasible; no sHNI upgrade. | P0 |
| SH-006 | Maximum possible upgrades | sHNI Preferred with funds/wallets for 4 | Create 4 minimum sHNI upgrades and stop. | P0 |
| SH-007 | Do not spend remainder | After maximum upgrades ₹1.10L remains | No automatic extra lots added. | P0 |
| SH-008 | Retail Only prevents upgrade | Mode Retail Only | No upgrade even with ₹10L free. | P0 |

# Multi-IPO

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| MI-001 | Higher GMP fully prioritized under scarcity | A 35%, B 22%; 17 PANs; 20 Retail slots total | Attempt up to 17 A rows first, then remaining ~3 B rows. | P0 |
| MI-002 | Lower GMP manually selected still participates | A 30%, C 10% manually APPLY | C planned after A with remaining resources. | P0 |
| MI-003 | High GMP manually SKIP excluded | A 40% but SKIP; B 25% selected | A ignored; B planned. | P0 |
| MI-004 | Cash reusable after earlier allotment | A release expected before B cutoff | Same bank cash may fund B. | P0 |
| MI-005 | Cash not reusable before release | A still blocked at B cutoff | B must use other available cash. | P0 |
| MI-006 | Baseline before sHNI phase | A and B selected; B can get Retail if cash remains before A sHNI upgrades consume it | Complete baseline pass through selected IPOs before sHNI upgrade pass. | P0 |
| MI-007 | Same time shares trackers | A and B same cutoff | Every A placement immediately affects B cash/limits. | P0 |
| MI-008 | Different cutoffs future EMI | EMI occurs between A and B cutoff | A sees pre-EMI cash; B sees post-EMI cash. | P0 |

# Locked & Manual

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| LM-001 | Locked row preserved | User locks bank/UPI | Re-plan leaves mapping unchanged. | P0 |
| LM-002 | Locked insufficient balance | Locked quote > available | Keep row visible with blocking warning. | P0 |
| LM-003 | Locked UPI limit exceeded | Locked wallet over limit | Keep row; blocking warning. | P0 |
| LM-004 | Manual bank change valid | User changes bank to feasible wallet | Revalidate and keep edit. | P0 |
| LM-005 | Manual bank change cross-funded | User chooses other person bank | Keep if allowed; show cross-funding warning. | P0 |
| LM-006 | Manual category Retail→sHNI | User changes category | Recalculate min sHNI lots/amount; validate; no second row. | P0 |
| LM-007 | Manual lots increase | User increases lots | Recalculate cash and rolling amount usage immediately. | P0 |
| LM-008 | Manual unselect IPO | Existing draft plan contains rows; user unselects IPO | Rows removed from new plan and resources returned. | P0 |

# Repair & Rehome

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| RR-001 | Rehome one Retail to free sHNI bank | Large bank fragmented by Retail; alternative small bank exists | Move Retail, place sHNI, all rows remain valid. | P1 |
| RR-002 | Repair rollback when rehome fails | Displaced Retail has no valid destination | Rollback entire change; original plan restored. | P1 |
| RR-003 | Bounded rehome only | More than configured maximum rows would need moving | Do not perform complex upgrade; keep stable plan. | P1 |
| RR-004 | Owner-affinity equal-size swap | Two unlocked equal rows can swap to improve own mapping | Swap if all policies/limits remain valid. | P1 |
| RR-005 | No swap on locked row | One row locked | Do not swap. | P1 |

# Audit & Determinism

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| AD-001 | Detect duplicate PAN/IPO | Force two rows same PAN/IPO into audit input | Audit fails blocking. | P0 |
| AD-002 | Detect cash double-spend | Two overlapping rows exceed bank cash | Audit fails blocking. | P0 |
| AD-003 | Detect rolling bank cap | Optimizer bug creates 7th bank application | Audit fails blocking. | P0 |
| AD-004 | Detect recurring debit omission | Plan spends money reserved by due EMI | Audit fails. | P0 |
| AD-005 | Deterministic repeated run | Same snapshot run 20 times | Logical plan identical every time. | P0 |
| AD-006 | DB input order independence | Shuffle banks/UPIs/applicants before planning | Output unchanged. | P0 |
| AD-007 | Version metadata stored | Successful planner run | planner_version, settings_version, snapshot hash, output hash stored. | P0 |

# End-to-End

| ID | Scenario | Key setup | Expected result | Pri |
| --- | --- | --- | --- | --- |
| EE-001 | 17-PAN all Retail one IPO | 17 active PANs, enough resources | 17 valid rows, one per PAN. | P0 |
| EE-002 | 17-PAN scarce cash | Only enough cash/slots for 12 | 12 highest-priority feasible PANs covered; 5 UNCOVERED_PAN. | P0 |
| EE-003 | 17-PAN sHNI Preferred | Enough baseline + several sHNI opportunities | Full feasible baseline then maximum minimum-sHNI upgrades by applicant priority. | P0 |
| EE-004 | Three IPO + wife/mother + EMI | Three selected IPOs, preferred cross funding, owner reserve, EMI between cutoffs | Plan respects high-GMP order, wife reserve, funding preference and EMI timeline. | P0 |
| EE-005 | Allotment then next-day reuse | Earlier IPO allotment recorded and later IPO next day | Debit/unblock reflected; released cash available for later plan. | P0 |
| EE-006 | Manual review/export readiness | User edits several rows and locks them | Final audit passes; export contains exactly locked/validated mappings. | P0 |

# Golden historical scenario template

Create one record per historical IPO planning day that you know well. These tests are more valuable than synthetic cases because they reveal whether Planner v2 matches your real operating behavior.

| Field | What to capture |
| --- | --- |
| Snapshot date/time | Exact planning time used for balances, blocks and limits. |
| Selected IPOs | IPO, GMP %, cutoff, allotment date, application mode, manual APPLY/SKIP state. |
| Applicants | PAN alias, priority, demat, active status. |
| Banks/UPIs | Owner, balance, active state, UPI, rolling usage, cross-funding setting. |
| Funding preferences | Beneficiary → preferred banks and order. |
| Recurring debits | Any EMI/other debit before relevant cutoffs. |
| Existing blocks | Amount, IPO, expected release boundary. |
| Expected plan | Applicant → IPO → category → lots → bank → UPI. |
| Expected uncovered rows | Any PAN/IPO that should intentionally remain uncovered. |
| Reason | Why this expected result is correct in business terms. |

# Release gate

- P0: 100% pass required for private beta.

- Golden historical cases: 100% reviewed; differences must be intentional and documented.

- P1: target 100% before invitation beta.

- P2: may be staged, but no known P2 defect may cause wrong cash, duplicate PAN applications or silent override of user locks.

- Planner audit must fail closed: export is blocked when any blocking audit error exists.
