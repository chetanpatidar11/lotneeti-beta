"""Background registrar lookups: UUID task arguments only, no money mutations."""

import json
import time

from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from applications.allotment import fingerprint, identity_hash, match_bids
from applications.models import AllotmentCheck, Application
from applications.registrars import PROVIDERS, RegistrarError, catalogue, lookup, resolve_issue
from core.crypto import decrypt_value, encrypt_value


@shared_task(soft_time_limit=900, time_limit=930, ignore_result=True)
def check_allotments(check_id):
    # A duplicate broker delivery must not launch another PAN batch.
    with transaction.atomic():
        job = AllotmentCheck.objects.select_for_update().get(pk=check_id)
        if job.status != "QUEUED":
            return
        job.status = "RUNNING"
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])
    try:
        catalogues = {provider: catalogue(provider) for provider in PROVIDERS}
        sources = {}
        for query in job.queries.select_related("ipo", "applicant").order_by("pk"):
            query.state = "CHECKING"
            query.save(update_fields=["state"])
            try:
                if query.ipo_id not in sources:
                    sources[query.ipo_id] = resolve_issue(query.ipo, catalogues)
                source = sources[query.ipo_id]
                if source is None:
                    raise RegistrarError("UNSUPPORTED")
                provider, issue_id = source
                query.provider = provider
                # Global per-provider budget, including concurrent workspace jobs.
                if not cache.add(f"allotment:provider:v1:{provider}", True, timeout=1):
                    raise RegistrarError("RATE_LIMITED")
                pan = decrypt_value(query.applicant.pan_ciphertext, purpose="pan")
                bids = lookup(provider, issue_id, pan)
                query.records_ciphertext = encrypt_value(
                    json.dumps([bid.data() for bid in bids]), purpose="allotment-result"
                )
                query.state = "FOUND" if bids else "NOT_FOUND"
                applications = list(
                    Application.objects.filter(
                        workspace_id=job.workspace_id,
                        ipo=query.ipo,
                        applicant=query.applicant,
                    ).select_related("ipo", "applicant", "demat")
                )
                matched = (
                    match_bids(applications, bids)
                    if query.identity_hash
                    == identity_hash(
                        job.workspace_id,
                        query.ipo_id,
                        query.applicant_id,
                    )
                    else {}
                )
                by_id = {item.pk: item for item in applications}
                for review in query.reviews.all():
                    item = by_id.get(review.application_id)
                    if item is not None and fingerprint(item) == review.fingerprint:
                        review.matched_index = matched.get(item.pk)
                        review.save(update_fields=["matched_index"])
            except RegistrarError as exc:
                query.state = exc.state
            except Exception:
                # Never persist third-party errors that might echo private inputs.
                query.state = "UNAVAILABLE"
            query.checked_at = timezone.now()
            query.save(update_fields=["state", "provider", "records_ciphertext", "checked_at"])
            time.sleep(1.05)
        job.status = "DONE"
    except Exception:
        job.queries.filter(state__in=["QUEUED", "CHECKING"]).update(state="UNAVAILABLE")
        job.status = "FAILED"
    finally:
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])


@shared_task(ignore_result=True)
def expire_allotment_results():
    from datetime import timedelta

    from applications.models import AllotmentQuery

    return (
        AllotmentQuery.objects.filter(
            batch__created_at__lt=timezone.now() - timedelta(days=7),
        )
        .exclude(records_ciphertext="")
        .update(records_ciphertext="")
    )
