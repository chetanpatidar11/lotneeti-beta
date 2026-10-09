"""Local ingestion boundary for normalized, permitted IPO feed records.

No network client or automatic matching is provided. A caller must identify the
canonical IPO before recording an external source observation.
"""

from collections.abc import Mapping
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.audit import record_event
from ipos.dto import IPORecord
from ipos.models import IPO, IPOSourceLink, IPOSourceSnapshot

EXCHANGE_SOURCE_KEYS = frozenset({"nse", "bse", "sebi"})


class NormalizedExchangeIPOProvider:
    """Accept canonical fields from a separately approved feed or local fixture."""

    def __init__(self, key: str):
        if key not in EXCHANGE_SOURCE_KEYS:
            raise ValueError("Unsupported exchange source")
        self.key = key

    def normalize(
        self, raw: Mapping[str, object], *, source_record_id: str, observed_at: datetime
    ) -> IPORecord:
        return IPORecord.from_mapping(
            raw,
            source_key=self.key,
            source_record_id=source_record_id,
            observed_at=observed_at,
        )


@transaction.atomic
def record_exchange_snapshot(*, ipo: IPO, record: IPORecord) -> IPOSourceSnapshot:
    """Store a normalized observation without changing the published IPO."""

    if ipo._state.adding:
        raise ValidationError("A saved canonical IPO is required")
    if record.source_key not in EXCHANGE_SOURCE_KEYS:
        raise ValidationError("Unsupported exchange source")
    # Reuse model field and cross-field validation without creating a second IPO.
    candidate = IPO(**record.model_fields())
    candidate.full_clean(validate_unique=False, validate_constraints=False)
    link, _ = IPOSourceLink.objects.get_or_create(
        source_key=record.source_key,
        source_record_id=record.source_record_id,
        defaults={"ipo": ipo},
    )
    if link.ipo_id != ipo.pk:
        raise ValidationError("Source identity is already linked to a different IPO")
    snapshot, _ = IPOSourceSnapshot.objects.get_or_create(
        link=link,
        payload_hash=record.payload_hash,
        observed_at=record.source_observed_at,
        defaults={"payload": record.payload()},
    )
    return snapshot


@transaction.atomic
def set_canonical_source_enabled(
    *, link: IPOSourceLink, enabled: bool, rights_reference: str, actor
) -> IPOSourceLink:
    """Explicitly gate reuse of a linked feed in effective IPO facts."""

    if not actor.is_staff or not actor.is_founder_admin:
        raise ValidationError("Founder access is required")
    reference = rights_reference.strip()
    if enabled and not reference:
        raise ValidationError("Documented source-use permission is required")
    if len(reference) > 250:
        raise ValidationError("Permission reference is too long")
    locked = IPOSourceLink.objects.select_for_update().get(pk=link.pk)
    locked.canonical_enabled = enabled
    if enabled:
        locked.rights_reference = reference
        locked.approved_by = actor
        locked.approved_at = timezone.now()
    locked.save(
        update_fields=["canonical_enabled", "rights_reference", "approved_by", "approved_at"]
    )
    record_event(
        action="ipo.source_canonical_enabled" if enabled else "ipo.source_canonical_disabled",
        target=locked,
        actor=actor,
        metadata={"source_key": locked.source_key, "source_record_id": locked.source_record_id},
    )
    return locked
