"""PAN lookup staging and explicitly reviewed, atomic result recording."""

import hashlib
import json
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from applications.models import AllotmentCheck, AllotmentQuery, AllotmentReview, Application
from applications.registrars import identifier
from applications.services import _require_writer, mark_allotted, mark_blocked, mark_not_allotted
from core.audit import record_event
from core.crypto import decrypt_value
from funding.models import BankAccount
from ipos.models import IPO
from ipos.overrides import effective_ipo_values

PENDING = (Application.Status.SUBMITTED, Application.Status.BLOCKED)
MESSAGES = {
    "QUEUED": "Waiting to check",
    "CHECKING": "Checking registrar",
    "FOUND": "Review result",
    "NOT_FOUND": "No matching bid returned; verify manually",
    "UNAVAILABLE": "Registrar unavailable; retry later or enter a verified result",
    "UNSUPPORTED": "Automatic lookup unavailable for this IPO; enter a verified result",
    "CHALLENGE": "Registrar requires verification; check there and enter the result",
    "PENDING": "Results not published yet",
    "RATE_LIMITED": "Registrar busy; retry later",
    "REVIEW": "Registrar response needs manual review",
}


def fingerprint(item):
    values = [
        str(getattr(item, field))
        for field in (
            "pk",
            "ipo_id",
            "applicant_id",
            "demat_id",
            "bank_id",
            "upi_id",
            "category",
            "lots",
            "amount",
            "status",
            "edited_at",
            "submitted_at",
            "blocked_at",
            "result_at",
        )
    ]
    values += [
        item.applicant.pan_lookup_hash,
        item.demat.dp_id_ciphertext,
        item.demat.client_id_ciphertext,
        str(item.ipo.lot_size),
        str(effective_ipo_values(item.ipo)["upper_price"]),
    ]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def identity_hash(workspace_id, ipo_id, applicant_id):
    values = []
    for item in (
        Application.objects.filter(
            workspace_id=workspace_id,
            ipo_id=ipo_id,
            applicant_id=applicant_id,
        )
        .select_related("applicant", "demat")
        .order_by("pk")
    ):
        values.append(
            [
                str(item.pk),
                str(item.demat_id),
                item.category,
                item.lots,
                str(item.amount),
                str(item.edited_at),
                str(item.cancelled_at),
                item.applicant.pan_lookup_hash,
                item.demat.dp_id_ciphertext,
                item.demat.client_id_ciphertext,
            ]
        )
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def expire_stale_checks(workspace):
    cutoff = timezone.now() - timedelta(minutes=20)
    stale = AllotmentCheck.objects.filter(workspace=workspace).filter(
        Q(status="QUEUED", created_at__lt=cutoff) | Q(status="RUNNING", started_at__lt=cutoff)
    )
    ids = list(stale.values_list("pk", flat=True))
    stale.update(status="FAILED", completed_at=timezone.now())
    AllotmentQuery.objects.filter(
        batch_id__in=ids, batch__status="FAILED", state__in=["QUEUED", "CHECKING"]
    ).update(state="UNAVAILABLE")


def records(query):
    if not query.records_ciphertext:
        return []
    return json.loads(decrypt_value(query.records_ciphertext, purpose="allotment-result"))


def match_bids(applications, bids):
    """Only mutually unique matches; response order and category defaults are never evidence.

    Include completed lanes in applications, so a lone pending shareholder cannot
    accidentally consume the public result already recorded on the same PAN.
    """
    candidates = []
    for bid in bids:
        matches = []
        for item in applications:
            if bid.category and bid.category != item.category:
                continue
            if bid.applied is not None and bid.applied != item.lots * item.ipo.lot_size:
                continue
            if bid.demat:
                dp = decrypt_value(item.demat.dp_id_ciphertext, purpose="demat")
                client = decrypt_value(item.demat.client_id_ciphertext, purpose="demat")
                # NSDL uses DP+client, CDSL uses its full beneficiary client ID.
                expected = client if item.demat.depository == "CDSL" else dp + client
                if identifier(bid.demat) != identifier(expected):
                    continue
            if bid.quantity > item.lots * item.ipo.lot_size:
                continue
            matches.append(item.pk)
        candidates.append(matches)
    result = {}
    for index, matches in enumerate(candidates):
        if len(matches) == 1 and sum(matches[0] in other for other in candidates) == 1:
            result[matches[0]] = index
    return result


@transaction.atomic
def create_check(*, workspace, actor, ipo_ids):
    _require_writer(workspace, actor)
    # Serialize starts for the tenant; double clicks do not create two provider batches.
    from accounts.models import Workspace

    Workspace.objects.select_for_update().get(pk=workspace.pk)
    expire_stale_checks(workspace)
    active = AllotmentCheck.objects.filter(
        workspace=workspace,
        status__in=["QUEUED", "RUNNING"],
    ).first()
    if active:
        return active, False
    qs = Application.objects.filter(workspace=workspace, status__in=PENDING)
    if ipo_ids:
        qs = qs.filter(ipo_id__in=ipo_ids)
    items = list(
        qs.select_related("ipo", "applicant", "demat").order_by("ipo_id", "applicant_id", "pk")[
            :501
        ]
    )
    if not items:
        raise ValidationError(
            "No submitted or blocked applications to check. Mark applied bids submitted first."
        )
    groups = {(item.ipo_id, item.applicant_id) for item in items}
    if len(items) > 500 or len(groups) > 100:
        raise ValidationError(
            "Check up to 100 accounts / IPOs at once. Select one IPO to narrow the check."
        )
    job = AllotmentCheck.objects.create(workspace=workspace, created_by=actor)
    queries = {}
    for item in items:
        key = (item.ipo_id, item.applicant_id)
        if key not in queries:
            queries[key] = AllotmentQuery.objects.create(
                batch=job,
                ipo=item.ipo,
                applicant=item.applicant,
                identity_hash=identity_hash(workspace.pk, item.ipo_id, item.applicant_id),
            )
        AllotmentReview.objects.create(
            query=queries[key], application=item, fingerprint=fingerprint(item)
        )
    record_event(
        action="allotment.check_started",
        target=job,
        actor=actor,
        workspace=workspace,
        metadata={"queries": len(queries), "bids": len(items)},
    )
    return job, True


@transaction.atomic
def record_results(*, check, actor, rows):
    _require_writer(check.workspace, actor)
    # Lock the batch first so retries cannot pass the recorded marker concurrently.
    job = AllotmentCheck.objects.select_for_update().get(pk=check.pk)
    if job.status not in {"DONE", "FAILED"}:
        raise ValidationError("Wait for this check to finish before recording results.")
    if job.created_at < timezone.now() - timedelta(days=7):
        raise ValidationError("This check has expired. Run a fresh check before recording.")
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValidationError("Select each application once.")
    reviews = {
        r.pk: r
        for r in AllotmentReview.objects.select_for_update(of=("self",))
        .filter(
            query__batch=job,
            pk__in=ids,
        )
        .select_related("query")
    }
    if len(reviews) != len(rows):
        raise ValidationError("Some results do not belong to this check.")
    applications = {
        a.pk: a
        for a in Application.objects.select_for_update(of=("self",))
        .filter(
            workspace=job.workspace,
            pk__in=[r.application_id for r in reviews.values()],
        )
        .select_related("ipo", "applicant", "demat")
        .order_by("pk")
    }
    # The existing allotted service locks Application -> IPO -> Bank. Follow
    # the same order before invoking it, including concurrent single-row calls.
    list(
        IPO.objects.select_for_update()
        .filter(pk__in={a.ipo_id for a in applications.values()})
        .order_by("pk")
    )
    list(
        BankAccount.objects.select_for_update()
        .filter(pk__in={a.bank_id for a in applications.values()})
        .order_by("pk")
    )
    used = {
        (r.query_id, r.recorded_index): r.pk
        for r in AllotmentReview.objects.filter(
            query__batch=job,
            recorded_at__isnull=False,
            recorded_index__isnull=False,
        )
    }
    changed = []
    for row in rows:
        review = reviews[row["id"]]
        item = applications[review.application_id]
        quantity, cost, index = row["quantity"], row["actual_cost"], row.get("source_index")
        if review.recorded_at:
            if (quantity, cost, index) != (
                review.recorded_quantity,
                review.recorded_cost,
                review.recorded_index,
            ):
                raise ValidationError("A recorded result cannot be replaced. Refresh Applications.")
            changed.append(item)
            continue
        if item.status not in PENDING or fingerprint(item) != review.fingerprint:
            raise ValidationError(
                "Application details changed since this check. Run a fresh check."
            )
        if review.query.identity_hash != identity_hash(
            job.workspace_id,
            review.query.ipo_id,
            review.query.applicant_id,
        ):
            raise ValidationError("Bid mappings changed since this check. Run a fresh check.")
        bids = records(review.query)
        if index is not None:
            if index >= len(bids):
                raise ValidationError("Choose a result returned by this registrar.")
            key = (review.query_id, index)
            if key in used and used[key] != review.pk:
                raise ValidationError(
                    "The same registrar bid cannot be recorded against two applications."
                )
            used[key] = review.pk
        if review.matched_index is None or index != review.matched_index:
            if not row.get("manual_verified", False):
                raise ValidationError(
                    "Verify the bid identity before recording an unmatched result."
                )
        if quantity > item.lots * item.ipo.lot_size:
            raise ValidationError("Allotted shares cannot exceed applied shares.")
        if (quantity == 0 and cost != 0) or (quantity > 0 and (cost <= 0 or cost > item.amount)):
            raise ValidationError("Check the allotted quantity and amount.")
        if item.status == Application.Status.SUBMITTED:
            item = mark_blocked(application=item, actor=actor, record_only=True)
        if quantity == 0:
            item = mark_not_allotted(application=item, actor=actor)
        else:
            item = mark_allotted(application=item, actor=actor, quantity=quantity, actual_cost=cost)
        review.recorded_at = timezone.now()
        review.recorded_quantity = quantity
        review.recorded_cost = cost
        review.recorded_index = index
        review.save(
            update_fields=["recorded_at", "recorded_quantity", "recorded_cost", "recorded_index"]
        )
        record_event(
            action="allotment.review_recorded",
            target=review,
            actor=actor,
            workspace=job.workspace,
            metadata={"manual_verified": row.get("manual_verified", False)},
        )
        changed.append(item)
    return changed
