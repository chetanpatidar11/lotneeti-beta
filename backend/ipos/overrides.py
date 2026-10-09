"""Audited IPO field corrections layered over immutable provider/source values."""

from copy import copy
from dataclasses import replace

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import CharField, F, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.audit import record_event
from ipos.canonical import CanonicalIPOResolution, resolve_canonical_ipo
from ipos.models import IPO, IPOFieldOverride

OVERRIDABLE_FIELDS = frozenset(
    {
        "issuer_name",
        "symbol",
        "issue_type",
        "lower_price",
        "upper_price",
        "lot_size",
        "open_date",
        "close_date",
        "allotment_date",
        "listing_date",
        "status",
        "publication_state",
    }
)


def effective_ipo_resolution(ipo: IPO) -> CanonicalIPOResolution:
    canonical = resolve_canonical_ipo(ipo)
    values = {**canonical.values, "publication_state": ipo.publication_state}
    fields = dict(canonical.fields)
    for override in ipo.field_overrides.filter(resumed_at__isnull=True):
        field = IPO._meta.get_field(override.field_name)
        values[override.field_name] = field.to_python(
            None if override.value == "" and field.null else override.value
        )
        if override.field_name in fields:
            fields[override.field_name] = replace(
                fields[override.field_name],
                value=values[override.field_name],
                selected_source="manual",
                provenance_source="manual",
            )
    candidate = copy(ipo)
    for name, value in values.items():
        setattr(candidate, name, value)
    try:
        candidate.clean()
    except ValidationError:
        # A later feed update cannot make a previously valid manual correction
        # break the published IPO or the planner. Keep cached facts instead.
        values = {name: getattr(ipo, name) for name in OVERRIDABLE_FIELDS}
        fields = {
            name: replace(
                item, value=values[name], selected_source="cached", provenance_source="cached"
            )
            for name, item in fields.items()
        }
        for override in ipo.field_overrides.filter(resumed_at__isnull=True):
            field = IPO._meta.get_field(override.field_name)
            values[override.field_name] = field.to_python(
                None if override.value == "" and field.null else override.value
            )
            if override.field_name in fields:
                fields[override.field_name] = replace(
                    fields[override.field_name],
                    value=values[override.field_name],
                    selected_source="manual",
                    provenance_source="manual",
                )
        return CanonicalIPOResolution(values, fields, validation_blocked=True)
    return CanonicalIPOResolution(values, fields, canonical.validation_blocked)


def effective_ipo_values(ipo: IPO) -> dict:
    return effective_ipo_resolution(ipo).values


def published_ipos():
    publication_override = IPOFieldOverride.objects.filter(
        ipo_id=OuterRef("pk"), field_name="publication_state", resumed_at__isnull=True
    ).values("value")[:1]
    return IPO.objects.annotate(
        effective_publication_state=Coalesce(
            Subquery(publication_override), F("publication_state"), output_field=CharField()
        )
    ).filter(effective_publication_state=IPO.PublicationState.PUBLISHED)


def _validate_effective(ipo: IPO, values: dict) -> None:
    effective = copy(ipo)
    for name, value in values.items():
        setattr(effective, name, value)
    effective.clean()


@transaction.atomic
def set_ipo_override(*, ipo: IPO, field_name: str, value, reason: str, actor) -> IPOFieldOverride:
    if field_name not in OVERRIDABLE_FIELDS:
        raise ValidationError("This IPO field cannot be overridden")
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValidationError("A reason of up to 500 characters is required")
    locked = IPO.objects.select_for_update().get(pk=ipo.pk)
    field = IPO._meta.get_field(field_name)
    converted = field.clean(value, locked)
    values = effective_ipo_values(locked)
    values[field_name] = converted
    _validate_effective(locked, values)
    now = timezone.now()
    IPOFieldOverride.objects.filter(
        ipo=locked, field_name=field_name, resumed_at__isnull=True
    ).update(resumed_at=now, resumed_by=actor)
    override = IPOFieldOverride.objects.create(
        ipo=locked,
        field_name=field_name,
        value="" if converted is None else str(converted),
        reason=reason,
        created_by=actor,
    )
    record_event(
        action="ipo.override_set",
        target=override,
        actor=actor,
        metadata={"field": field_name},
    )
    return override


@transaction.atomic
def resume_ipo_auto(*, ipo: IPO, field_name: str, actor) -> None:
    if field_name not in OVERRIDABLE_FIELDS:
        raise ValidationError("This IPO field cannot be overridden")
    locked = IPO.objects.select_for_update().get(pk=ipo.pk)
    override = IPOFieldOverride.objects.filter(
        ipo=locked, field_name=field_name, resumed_at__isnull=True
    ).first()
    if override is None:
        raise ValidationError("This IPO field is already automatic")
    values = effective_ipo_values(locked)
    values[field_name] = resolve_canonical_ipo(locked).values.get(
        field_name, getattr(locked, field_name)
    )
    _validate_effective(locked, values)
    override.resumed_at = timezone.now()
    override.resumed_by = actor
    override.save(update_fields=["resumed_at", "resumed_by"])
    record_event(
        action="ipo.override_resumed",
        target=override,
        actor=actor,
        metadata={"field": field_name},
    )
