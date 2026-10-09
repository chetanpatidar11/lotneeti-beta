"""Immutable planner input contracts with canonical serialization.

This module deliberately has no Django imports. Snapshot construction happens
outside the selection engine, and identifiers are opaque strings.
"""

import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class IPOInput:
    id: str
    selected: bool
    gmp_percent: Decimal | None
    upper_price: Decimal
    lot_size: int
    cutoff_at: datetime
    allotment_date: date
    mode: str
    shni_cutoff_at: datetime | None = None


def application_cutoff(ipo: IPOInput, category: str) -> datetime:
    return ipo.shni_cutoff_at if category == "SHNI" and ipo.shni_cutoff_at else ipo.cutoff_at


@dataclass(frozen=True, slots=True)
class ApplicantInput:
    id: str
    priority: int
    active: bool


@dataclass(frozen=True, slots=True)
class DematInput:
    id: str
    applicant_id: str
    active: bool


@dataclass(frozen=True, slots=True)
class BankInput:
    id: str
    owner_id: str
    balance: Decimal
    active: bool
    cross_funding_policy: str
    restricted_applicant_id: str | None = None


@dataclass(frozen=True, slots=True)
class UPIInput:
    id: str
    bank_id: str
    holder_id: str
    active: bool
    verified: bool
    count_limit_override: int | None = None
    amount_limit_override: Decimal | None = None


@dataclass(frozen=True, slots=True)
class FundingPreferenceInput:
    beneficiary_id: str
    bank_id: str
    priority: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class RecurringDebitInput:
    id: str
    bank_id: str
    amount: Decimal
    frequency: str
    start_date: date
    next_due_date: date
    end_date: date | None
    active: bool


@dataclass(frozen=True, slots=True)
class CashBlockInput:
    id: str
    bank_id: str
    amount: Decimal
    blocked_at: datetime
    release_at: datetime | None


@dataclass(frozen=True, slots=True)
class RollingUsageInput:
    id: str
    bank_id: str
    upi_id: str
    amount: Decimal
    submitted_at: datetime
    cancelled: bool


@dataclass(frozen=True, slots=True)
class ExistingApplicationInput:
    id: str
    ipo_id: str
    applicant_id: str
    cancelled: bool


@dataclass(frozen=True, slots=True)
class LockedRowInput:
    id: str
    ipo_id: str
    applicant_id: str
    category: str
    lots: int
    amount: Decimal
    demat_id: str
    bank_id: str
    upi_id: str


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    version: str
    platform_cross_funding_policy: str
    workspace_cross_funding_policy: str
    upi_count_limit: int = 6
    bank_count_limit: int = 6
    upi_amount_limit: Decimal = Decimal("500000.00")
    bank_amount_limit: Decimal = Decimal("500000.00")
    rolling_window_hours: int = 24
    bank_level_enforcement: bool = True
    plan_cross_funding_override: str = "DEFAULT"


@dataclass(frozen=True, slots=True)
class PlannerSnapshot:
    as_of: datetime
    config: PlannerConfig
    ipos: tuple[IPOInput, ...] = ()
    applicants: tuple[ApplicantInput, ...] = ()
    demats: tuple[DematInput, ...] = ()
    banks: tuple[BankInput, ...] = ()
    upis: tuple[UPIInput, ...] = ()
    funding_preferences: tuple[FundingPreferenceInput, ...] = ()
    recurring_debits: tuple[RecurringDebitInput, ...] = ()
    cash_blocks: tuple[CashBlockInput, ...] = ()
    rolling_usage: tuple[RollingUsageInput, ...] = ()
    existing_applications: tuple[ExistingApplicationInput, ...] = ()
    locked_rows: tuple[LockedRowInput, ...] = ()

    def __post_init__(self):
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("Planner snapshot time must have a timezone")
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name not in {"as_of", "config"} and not isinstance(value, tuple):
                raise TypeError(f"{field.name} must be an immutable tuple")
        canonical_json(self)


def _canonical(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value else "0"
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Planner times must have a timezone")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        encoded = [_canonical(item) for item in value]
        if encoded and all(isinstance(item, dict) and "id" in item for item in encoded):
            encoded.sort(key=lambda item: item["id"])
        elif encoded and all(
            isinstance(item, dict) and "beneficiary_id" in item and "bank_id" in item
            for item in encoded
        ):
            encoded.sort(
                key=lambda item: (item["beneficiary_id"], item["priority"], item["bank_id"])
            )
        return encoded
    if value is None or isinstance(value, str | int | bool):
        return value
    raise TypeError(f"Unsupported planner input type: {type(value).__name__}")


def canonical_json(value: object) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
