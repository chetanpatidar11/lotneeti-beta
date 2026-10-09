"""Resolve reviewed IPO facts from immutable source snapshots.

This module never changes a cached IPO row. Missing data, conflicting exchanges,
and provider failures therefore leave the last valid canonical facts available.
"""

from copy import copy
from dataclasses import dataclass, replace

from django.core.exceptions import ValidationError

from ipos.models import IPO

SOURCE_FACT_FIELDS = frozenset(
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
    }
)
DOCUMENT_FACT_FIELDS = SOURCE_FACT_FIELDS - {"symbol", "status"}


@dataclass(frozen=True)
class FieldSource:
    value: object
    selected_source: str
    provenance_source: str
    source_values: dict[str, object]
    exchange_conflict: bool = False
    document_disagreement: bool = False


@dataclass(frozen=True)
class CanonicalIPOResolution:
    values: dict[str, object]
    fields: dict[str, FieldSource]
    validation_blocked: bool = False

    @property
    def exchange_conflict_fields(self) -> tuple[str, ...]:
        return tuple(sorted(name for name, item in self.fields.items() if item.exchange_conflict))

    @property
    def document_disagreement_fields(self) -> tuple[str, ...]:
        return tuple(
            sorted(name for name, item in self.fields.items() if item.document_disagreement)
        )


def _latest_snapshots(ipo: IPO) -> dict[str, object]:
    latest = {}
    snapshots = ipo.source_links.filter(
        source_key__in=("nse", "bse", "sebi"), canonical_enabled=True
    ).values_list(
        "snapshots__observed_at",
        "snapshots__fetched_at",
        "snapshots__id",
        "source_key",
        "snapshots__payload",
    )
    for observed_at, fetched_at, snapshot_id, source_key, payload in snapshots:
        if snapshot_id is None:
            continue
        rank = (observed_at, fetched_at, str(snapshot_id))
        if source_key not in latest or rank > latest[source_key][0]:
            latest[source_key] = (rank, payload)
    return {key: value[1] for key, value in latest.items()}


def resolve_canonical_ipo(ipo: IPO) -> CanonicalIPOResolution:
    """Choose each field while retaining all source values and cached fallback."""

    snapshots = _latest_snapshots(ipo)
    values = {name: getattr(ipo, name) for name in SOURCE_FACT_FIELDS}
    fields = {}
    for name in sorted(SOURCE_FACT_FIELDS):
        field = IPO._meta.get_field(name)
        source_values = {"cached": values[name]}
        for key in ("nse", "bse", "sebi"):
            payload = snapshots.get(key, {})
            provided = payload.get("provided_fields")
            raw = payload.get(name) if provided is None or name in provided else None
            if raw is not None and raw != "":
                source_values[key] = field.to_python(raw)

        nse = source_values.get("nse")
        bse = source_values.get("bse")
        sebi = source_values.get("sebi")
        conflict = nse is not None and bse is not None and nse != bse
        if conflict:
            chosen = "cached"
        elif nse is not None:
            chosen = "nse"
        elif bse is not None:
            chosen = "bse"
        elif sebi is not None:
            chosen = "sebi"
        else:
            chosen = "cached"

        value = source_values[chosen]
        provenance = (
            "sebi"
            if name in DOCUMENT_FACT_FIELDS and sebi is not None and sebi == value
            else chosen
        )
        document_disagreement = name in DOCUMENT_FACT_FIELDS and sebi is not None and sebi != value
        fields[name] = FieldSource(
            value=value,
            selected_source=chosen,
            provenance_source=provenance,
            source_values=source_values,
            exchange_conflict=conflict,
            document_disagreement=document_disagreement,
        )
        values[name] = value

    candidate = copy(ipo)
    for name, value in values.items():
        setattr(candidate, name, value)
    try:
        candidate.clean()
    except ValidationError:
        # Mixed source fields must never yield an invalid plan input.
        values = {name: getattr(ipo, name) for name in SOURCE_FACT_FIELDS}
        fields = {
            name: replace(
                item, value=values[name], selected_source="cached", provenance_source="cached"
            )
            for name, item in fields.items()
        }
        return CanonicalIPOResolution(values, fields, validation_blocked=True)
    return CanonicalIPOResolution(values, fields)
