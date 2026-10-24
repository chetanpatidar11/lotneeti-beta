"""Opt-in quota overlay. The Retail/sHNI engine and its input contracts stay unchanged.

Run the legacy engine first, keep every normal mapping fixed, then consider bHNI
replacements and additional shareholder rows. Audit shareholder rows as a separate
virtual issue; ASBA amounts reserve cash but never consume UPI limits.
"""

from collections import Counter
from dataclasses import dataclass, replace
from decimal import ROUND_FLOOR, Decimal
from hashlib import sha256

from django.core.exceptions import ValidationError

from applications.models import Application
from funding.models import BankAccount
from funding.policy import resolve_cross_funding_policy
from investors.models import Investor
from ipos.models import IPO, IPOUserDecision
from ipos.quota_terms import confirmed_shareholder_quota, shareholder_terms_fingerprint
from planner.audit import AuditResult, audit_plan
from planner.cash import PlannedAllocation, cash_at_cutoff, expected_release_at
from planner.coverage import CoverageResult, CoverageRow, PlanReason, UncoveredApplicant
from planner.dto import CashBlockInput, ExistingApplicationInput, application_cutoff, canonical_json
from planner.engine import PlannerProposal, generate_proposal
from planner.manual_plan import review_manual_rows
from planner.ordering import selected_ipo_order

QUOTA_VERSION = "planner-v2.0+quota-v1"
SHARE = "SHARE"
BHNI = "BHNI"
PUBLIC = "PUBLIC"
SUFFIX = ":shareholder"


@dataclass(frozen=True, slots=True)
class QuotaIPO:
    id: str
    enabled: bool
    preferred: bool
    eligible: tuple[str, ...]
    minimum_lots: int
    maximum_amount: Decimal
    terms_url: str
    bhni_preferred: bool
    terms_current: bool = True


@dataclass(frozen=True, slots=True)
class QuotaContext:
    ipos: tuple[QuotaIPO, ...] = ()
    existing_share: tuple[ExistingApplicationInput, ...] = ()
    active_applicants: tuple[str, ...] = ()
    asba_banks: tuple[str, ...] = ()

    @property
    def active(self):
        return any((item.enabled and item.preferred) or item.bhni_preferred for item in self.ipos)


@dataclass(frozen=True, slots=True)
class QuotaIssue:
    code: str
    ipo_id: str = ""
    applicant_id: str = ""
    message: str = ""
    category: str = ""


def quota_context(workspace, snapshot) -> QuotaContext:
    ids = {item.id for item in snapshot.ipos}
    decisions = {
        str(item.ipo_id): item
        for item in IPOUserDecision.objects.filter(
            workspace=workspace, ipo_id__in=ids
        ).prefetch_related("shareholder_eligible")
    }
    active = tuple(
        str(pk)
        for pk in Investor.objects.filter(workspace=workspace, active=True, is_deleted=False)
        .order_by("id")
        .values_list("pk", flat=True)
    )
    rules = []
    for ipo in IPO.objects.filter(pk__in=ids).order_by("id"):
        decision = decisions.get(str(ipo.pk))
        eligible = (
            tuple(
                sorted(
                    str(item.pk)
                    for item in decision.shareholder_eligible.all()
                    if str(item.pk) in active and item.workspace_id == workspace.pk
                )
            )
            if decision
            else ()
        )
        current_terms = (
            not decision
            or decision.shareholder_terms_fingerprint == shareholder_terms_fingerprint(ipo)
        )
        if not current_terms:
            eligible = ()
        rules.append(
            QuotaIPO(
                str(ipo.pk),
                confirmed_shareholder_quota(ipo),
                bool(decision and decision.shareholder_preferred),
                eligible,
                ipo.shareholder_min_lots,
                ipo.shareholder_max_amount,
                ipo.shareholder_terms_url,
                bool(decision and decision.mode == "BHNI_PREFERRED"),
                current_terms,
            )
        )
    existing = tuple(
        ExistingApplicationInput(
            str(item.pk), str(item.ipo_id), str(item.applicant_id), item.status == "CANCELLED"
        )
        for item in Application.objects.filter(
            workspace=workspace, category=SHARE, ipo_id__in=ids
        ).order_by("id")
    )
    asba_banks = tuple(
        str(pk)
        for pk in BankAccount.objects.filter(
            workspace=workspace, active=True, is_placeholder=False, is_imported_reference=False
        )
        .order_by("id")
        .values_list("pk", flat=True)
    )
    return QuotaContext(tuple(rules), existing, active, asba_banks)


def has_quota_rows(rows):
    return any(row.category in {SHARE, BHNI} for row in rows)


def row_issue_codes(issues, row):
    return [
        item.code
        for item in issues
        if item.ipo_id == row.ipo_id
        and item.applicant_id == row.applicant_id
        and getattr(item, "category", "")
        in {"", row.category, PUBLIC if row.category != SHARE else SHARE}
    ]


def _share_row(row):
    return (
        replace(row, ipo_id=row.ipo_id + SUFFIX, category="RETAIL")
        if row.category == SHARE
        else row
    )


def _from_virtual_issue(issue):
    share = issue.ipo_id.endswith(SUFFIX)
    return QuotaIssue(
        issue.code,
        issue.ipo_id.removesuffix(SUFFIX),
        issue.applicant_id,
        issue.message,
        SHARE if share else PUBLIC,
    )


def _bhni_blocks(snapshot, rows):
    ipos = {item.id: item for item in snapshot.ipos}
    return tuple(
        CashBlockInput(
            f"quota-asba:{index}",
            row.bank_id,
            row.amount,
            application_cutoff(ipos[row.ipo_id], "SHNI"),
            expected_release_at(ipos[row.ipo_id].allotment_date, ipos[row.ipo_id].cutoff_at.tzinfo),
        )
        for index, row in enumerate(rows)
        if row.category == BHNI and row.ipo_id in ipos and row.amount > 0
    )


def _virtual_snapshot(snapshot, context, rows):
    rules = {item.id: item for item in context.ipos}
    virtual_ipos = tuple(
        replace(item, id=item.id + SUFFIX, mode="RETAIL_ONLY")
        for item in snapshot.ipos
        if item.id in rules and rules[item.id].enabled
    )
    return replace(
        snapshot,
        ipos=snapshot.ipos + virtual_ipos,
        cash_blocks=snapshot.cash_blocks + _bhni_blocks(snapshot, rows),
        existing_applications=snapshot.existing_applications
        + tuple(replace(item, ipo_id=item.ipo_id + SUFFIX) for item in context.existing_share),
        locked_rows=tuple(
            _share_row(item) for item in snapshot.locked_rows if item.category != BHNI
        ),
    )


def _allocations(snapshot, rows):
    ipos = {item.id: item for item in snapshot.ipos}
    return tuple(
        PlannedAllocation(
            str(index),
            row.bank_id,
            row.amount,
            application_cutoff(ipos[row.ipo_id], "SHNI" if row.category == BHNI else row.category),
            expected_release_at(ipos[row.ipo_id].allotment_date, ipos[row.ipo_id].cutoff_at.tzinfo),
        )
        for index, row in enumerate(rows)
        if row.ipo_id in ipos and row.amount > 0
    )


def audit_quota_rows(snapshot, rows, context):
    virtual = _virtual_snapshot(snapshot, context, rows)
    normal = tuple(_share_row(row) for row in rows if row.category != BHNI)
    result = audit_plan(
        virtual, normal, reported_planned_total=sum((row.amount for row in normal), Decimal("0"))
    )
    issues = [_from_virtual_issue(item) for item in result.issues]
    rules = {item.id: item for item in context.ipos}
    issues.extend(
        QuotaIssue(
            "SHAREHOLDER_TERMS_CHANGED",
            item.id,
            "",
            "Shareholder terms changed. Reconfirm eligible investors in IPO settings.",
            SHARE,
        )
        for item in context.ipos
        if item.preferred and not item.terms_current
    )
    ipos = {item.id: item for item in snapshot.ipos}
    banks = {item.id: item for item in snapshot.banks}
    demats = {item.id: item for item in snapshot.demats}
    existing_public = {
        (item.ipo_id, item.applicant_id)
        for item in snapshot.existing_applications
        if not item.cancelled
    }
    public_counts = Counter((row.ipo_id, row.applicant_id) for row in rows if row.category != SHARE)
    for index, row in enumerate(rows):

        def issue(code, message, row=row):
            issues.append(QuotaIssue(code, row.ipo_id, row.applicant_id, message, row.category))

        ipo = ipos.get(row.ipo_id)
        if row.category == SHARE:
            rule = rules.get(row.ipo_id)
            if not rule or not rule.enabled or row.applicant_id not in rule.eligible:
                issue(
                    "SHAREHOLDER_INELIGIBLE",
                    "Select this investor as eligible for this IPO's confirmed shareholder quota.",
                )
            elif row.lots < rule.minimum_lots or row.amount > rule.maximum_amount:
                issue(
                    "INVALID_CATEGORY",
                    "Shareholder lots must fit this IPO's minimum and maximum amount.",
                )
        if row.category == "SHNI" and row.amount > Decimal("1000000"):
            issue("INVALID_CATEGORY", "Choose bHNI and bank ASBA for an amount above ₹10,00,000.")
        if row.category != BHNI:
            continue
        bank, demat = banks.get(row.bank_id), demats.get(row.demat_id)
        if (
            public_counts[(row.ipo_id, row.applicant_id)] > 1
            or (row.ipo_id, row.applicant_id) in existing_public
        ):
            issue(
                "DUPLICATE_APPLICANT_IPO",
                "Choose one Retail, sHNI or bHNI application per investor and IPO.",
            )
        if ipo is None:
            issue("INVALID_IPO", "Choose a selected IPO.")
            continue
        if row.applicant_id not in context.active_applicants:
            issue("APPLICANT_INACTIVE", "Choose an active investor.")
        if demat is None or not demat.active or demat.applicant_id != row.applicant_id:
            issue("INVALID_DEMAT", "Choose the applicant's active demat.")
        if (
            bank is None
            or not bank.active
            or bank.owner_id != row.applicant_id
            or bank.restricted_applicant_id not in {None, row.applicant_id}
            or row.upi_id
            or row.bank_id not in context.asba_banks
        ):
            issue(
                "ASBA_OWN_BANK_REQUIRED",
                "bHNI requires the applicant's own active bank ASBA account, without UPI.",
            )
        if (
            type(row.lots) is not int
            or row.lots < 1
            or row.amount != ipo.upper_price * ipo.lot_size * row.lots
        ):
            issue("INVALID_AMOUNT", "Enter positive whole lots matching the IPO price.")
        if row.amount <= Decimal("1000000"):
            issue("INVALID_CATEGORY", "bHNI requires a whole-lot amount above ₹10,00,000.")
        if bank is not None:
            others = tuple(other for position, other in enumerate(rows) if position != index)
            if (
                cash_at_cutoff(
                    bank=bank,
                    cutoff=application_cutoff(ipo, "SHNI"),
                    blocks=snapshot.cash_blocks,
                    allocations=_allocations(snapshot, others),
                    recurring_debits=snapshot.recurring_debits,
                ).raw_available
                < row.amount
            ):
                issue(
                    "INSUFFICIENT_BALANCE",
                    "Bank Balance is below the bHNI amount after other commitments.",
                )
    for locked in snapshot.locked_rows:
        if locked.category != BHNI:
            continue
        matches = [
            row
            for row in rows
            if row.ipo_id == locked.ipo_id
            and row.applicant_id == locked.applicant_id
            and row.category == BHNI
        ]
        if (
            len(matches) != 1
            or not matches[0].locked
            or any(
                getattr(matches[0], field) != getattr(locked, field)
                for field in ("lots", "amount", "bank_id", "demat_id", "upi_id")
            )
        ):
            issues.append(
                QuotaIssue(
                    "LOCKED_ROW_CHANGED",
                    locked.ipo_id,
                    locked.applicant_id,
                    "The locked bHNI application changed.",
                    BHNI,
                )
            )
    unique = tuple(dict.fromkeys(issues))
    return AuditResult(not unique, unique, sum((row.amount for row in rows), Decimal("0")))


def review_quota_rows(snapshot, edited_rows, context):
    if not context.active and not any(item["category"] in {SHARE, BHNI} for item in edited_rows):
        return review_manual_rows(snapshot, edited_rows)
    selected = {item.id: item for item in snapshot.ipos}
    rows = []
    for item in edited_rows:
        ipo = selected.get(str(item["ipo"]))
        if ipo is None:
            raise ValidationError("A row refers to an unselected IPO.")
        category = item["category"]
        upi = str(item["upi"]) if item.get("upi") else ""
        rows.append(
            CoverageRow(
                ipo.id,
                str(item["applicant"]),
                category,
                item["lots"],
                item.get("amount", ipo.upper_price * ipo.lot_size * item["lots"]),
                str(item["demat"]),
                str(item["bank"]),
                upi,
                locked=item.get("locked", False),
            )
        )
    rows = tuple(rows)
    share_blocks = tuple(
        CashBlockInput(
            f"manual-share:{index}",
            row.bank_id,
            row.amount,
            selected[row.ipo_id].cutoff_at,
            expected_release_at(
                selected[row.ipo_id].allotment_date, selected[row.ipo_id].cutoff_at.tzinfo
            ),
        )
        for index, row in enumerate(rows)
        if row.category == SHARE and row.amount > 0
    )
    public_snapshot = replace(
        snapshot,
        cash_blocks=snapshot.cash_blocks + _bhni_blocks(snapshot, rows) + share_blocks,
        locked_rows=tuple(
            item for item in snapshot.locked_rows if item.category not in {SHARE, BHNI}
        ),
    )
    normal_edits = [item for item in edited_rows if item["category"] not in {SHARE, BHNI}]
    normal_reviewed, manual_audit = review_manual_rows(public_snapshot, normal_edits)
    warnings = {(row.ipo_id, row.applicant_id): row.warnings for row in normal_reviewed}
    banks = {item.id: item for item in snapshot.banks}

    def row_warnings(row):
        bank = banks.get(row.bank_id)
        if row.category == SHARE and bank:
            return resolve_cross_funding_policy(
                platform_default=snapshot.config.platform_cross_funding_policy,
                bank_policy=bank.cross_funding_policy,
                workspace_policy=snapshot.config.workspace_cross_funding_policy,
                plan_override=snapshot.config.plan_cross_funding_override,
                locked_row=row.locked,
                same_owner=bank.owner_id == row.applicant_id,
            ).warnings
        return warnings.get((row.ipo_id, row.applicant_id), ())

    rows = tuple(replace(row, warnings=row_warnings(row)) for row in rows)
    final = audit_quota_rows(snapshot, rows, context)
    extra = tuple(_from_virtual_issue(item) for item in manual_audit.issues)
    all_issues = tuple(dict.fromkeys((*final.issues, *extra)))
    return rows, replace(final, valid=not all_issues, issues=all_issues)


def _valid_candidate(snapshot, rows, context):
    return audit_quota_rows(snapshot, tuple(rows), context).valid


def generate_quota_proposal(snapshot, context):
    if not context.active and not has_quota_rows(snapshot.locked_rows):
        return generate_proposal(snapshot)
    external_locks = tuple(
        CoverageRow(
            item.ipo_id,
            item.applicant_id,
            item.category,
            item.lots,
            item.amount,
            item.demat_id,
            item.bank_id,
            item.upi_id,
            locked=True,
        )
        for item in snapshot.locked_rows
        if item.category in {SHARE, BHNI}
    )
    base_snapshot = replace(
        snapshot,
        locked_rows=tuple(
            item for item in snapshot.locked_rows if item.category not in {SHARE, BHNI}
        ),
        cash_blocks=snapshot.cash_blocks
        + tuple(
            CashBlockInput(
                f"quota-lock:{index}",
                row.bank_id,
                row.amount,
                application_cutoff(
                    next(ipo for ipo in snapshot.ipos if ipo.id == row.ipo_id),
                    "SHNI" if row.category == BHNI else "RETAIL",
                ),
                expected_release_at(
                    next(ipo for ipo in snapshot.ipos if ipo.id == row.ipo_id).allotment_date,
                    snapshot.as_of.tzinfo,
                ),
            )
            for index, row in enumerate(external_locks)
            if row.amount > 0
        ),
        existing_applications=snapshot.existing_applications
        + tuple(
            ExistingApplicationInput(f"quota-lock:{index}", row.ipo_id, row.applicant_id, False)
            for index, row in enumerate(external_locks)
            if row.category == BHNI
        ),
    )
    legacy = generate_proposal(base_snapshot)
    rows = list(legacy.coverage.rows) + list(external_locks)
    uncovered = list(legacy.coverage.uncovered)
    rules = {item.id: item for item in context.ipos}
    applicants = sorted(snapshot.applicants, key=lambda item: (item.priority, item.id))
    existing = {
        (item.ipo_id, item.applicant_id)
        for item in snapshot.existing_applications
        if not item.cancelled
    }
    for ipo in selected_ipo_order(snapshot.ipos):
        rule = rules.get(ipo.id)
        if not rule:
            continue
        if rule.bhni_preferred:
            unit = ipo.upper_price * ipo.lot_size
            lots = int((Decimal("1000000") / unit).to_integral_value(rounding=ROUND_FLOOR)) + 1
            for applicant in applicants:
                if (
                    applicant.id not in context.active_applicants
                    or (ipo.id, applicant.id) in existing
                ):
                    continue
                prior = [
                    row
                    for row in rows
                    if row.ipo_id == ipo.id
                    and row.applicant_id == applicant.id
                    and row.category != SHARE
                ]
                if any(row.locked for row in prior):
                    continue
                others = [row for row in rows if row not in prior]
                demats = sorted(
                    (
                        item
                        for item in snapshot.demats
                        if item.active and item.applicant_id == applicant.id
                    ),
                    key=lambda item: item.id,
                )
                if not demats:
                    continue
                for bank in sorted(
                    snapshot.banks,
                    key=lambda item: (item.id not in {row.bank_id for row in prior}, item.id),
                ):
                    if bank.owner_id != applicant.id or not bank.active:
                        continue
                    candidate = CoverageRow(
                        ipo.id,
                        applicant.id,
                        BHNI,
                        lots,
                        unit * lots,
                        demats[0].id,
                        bank.id,
                        "",
                        reasons=(
                            PlanReason(
                                "BANK_ASBA",
                                "Uses own-bank ASBA at the minimum whole-lot bHNI amount.",
                            ),
                        ),
                    )
                    if _valid_candidate(snapshot, others + [candidate], context):
                        rows = others + [candidate]
                        uncovered = [
                            item
                            for item in uncovered
                            if (item.ipo_id, item.applicant_id) != (ipo.id, applicant.id)
                        ]
                        break
        if not (rule.enabled and rule.preferred):
            continue
        existing_share = {
            (item.ipo_id, item.applicant_id)
            for item in context.existing_share
            if not item.cancelled
        }
        for applicant in applicants:
            if (
                applicant.id not in rule.eligible
                or (ipo.id, applicant.id) in existing_share
                or any(
                    row.ipo_id == ipo.id
                    and row.applicant_id == applicant.id
                    and row.category == SHARE
                    for row in rows
                )
            ):
                continue
            demats = sorted(
                (
                    item
                    for item in snapshot.demats
                    if item.active and item.applicant_id == applicant.id
                ),
                key=lambda item: item.id,
            )
            if not demats:
                uncovered.append(UncoveredApplicant(ipo.id, applicant.id, "SHAREHOLDER_NO_DEMAT"))
                continue
            unit = ipo.upper_price * ipo.lot_size
            maximum = int((rule.maximum_amount / unit).to_integral_value(rounding=ROUND_FLOOR))
            preferences = {
                item.bank_id: item.priority
                for item in snapshot.funding_preferences
                if item.beneficiary_id == applicant.id and item.enabled
            }
            candidates = []
            for bank in snapshot.banks:
                if not bank.active:
                    continue
                for upi in snapshot.upis:
                    if upi.bank_id != bank.id or not upi.active or not upi.verified:
                        continue
                    low, high, best = rule.minimum_lots, maximum, None
                    while low <= high:
                        lots = (low + high) // 2
                        candidate = CoverageRow(
                            ipo.id,
                            applicant.id,
                            SHARE,
                            lots,
                            unit * lots,
                            demats[0].id,
                            bank.id,
                            upi.id,
                            warnings=() if bank.owner_id == applicant.id else ("CROSS_FUNDING",),
                            reasons=(
                                PlanReason(
                                    "SHAREHOLDER_MAXIMUM",
                                    "Maximum affordable shareholder lots after the normal plan.",
                                ),
                            ),
                        )
                        if _valid_candidate(snapshot, rows + [candidate], context):
                            best, low = candidate, lots + 1
                        else:
                            high = lots - 1
                    if best:
                        candidates.append(
                            (
                                (
                                    -best.lots,
                                    bank.owner_id != applicant.id,
                                    bank.id not in preferences,
                                    preferences.get(bank.id, 0),
                                    upi.holder_id != applicant.id,
                                    bank.id,
                                    upi.id,
                                ),
                                best,
                            )
                        )
            if candidates:
                rows.append(min(candidates, key=lambda item: item[0])[1])
            else:
                uncovered.append(
                    UncoveredApplicant(
                        ipo.id, applicant.id, "SHAREHOLDER_INSUFFICIENT_FUNDS_OR_LIMITS"
                    )
                )
    result_rows = tuple(rows)
    audit = audit_quota_rows(snapshot, result_rows, context)

    def digest(value):
        return sha256(canonical_json(value).encode()).hexdigest()

    return PlannerProposal(
        QUOTA_VERSION,
        f"sha256:{digest((snapshot.config, context))}",
        digest((snapshot, context)),
        digest((QUOTA_VERSION, result_rows, audit)),
        CoverageResult(result_rows, tuple(uncovered)),
        audit,
    )
