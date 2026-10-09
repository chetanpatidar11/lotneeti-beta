"""Pure 24-hour submitted-application limit tracker."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from planner.dto import PlannerConfig, RollingUsageInput, UPIInput


@dataclass(frozen=True, slots=True)
class RollingCheck:
    allowed: bool
    blocking_reasons: tuple[str, ...]
    upi_count_after: int
    bank_count_after: int
    upi_amount_after: Decimal
    bank_amount_after: Decimal


@dataclass(frozen=True, slots=True)
class RollingLimitTracker:
    events: tuple[RollingUsageInput, ...] = ()

    def check(
        self, *, upi: UPIInput, amount: Decimal, at: datetime, config: PlannerConfig
    ) -> RollingCheck:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Application time must have a timezone")
        if amount <= 0:
            raise ValueError("Application amount must be positive")
        window_start = at - timedelta(hours=config.rolling_window_hours)
        active = [
            event
            for event in self.events
            if not event.cancelled and window_start < event.submitted_at <= at
        ]
        upi_events = [event for event in active if event.upi_id == upi.id]
        bank_events = [event for event in active if event.bank_id == upi.bank_id]
        upi_count = len(upi_events) + 1
        bank_count = len(bank_events) + 1
        upi_amount = sum((event.amount for event in upi_events), Decimal("0.00")) + amount
        bank_amount = sum((event.amount for event in bank_events), Decimal("0.00")) + amount
        upi_count_limit = (
            upi.count_limit_override
            if upi.count_limit_override is not None
            else config.upi_count_limit
        )
        upi_amount_limit = (
            upi.amount_limit_override
            if upi.amount_limit_override is not None
            else config.upi_amount_limit
        )
        reasons = []
        if upi_count > upi_count_limit or upi_amount > upi_amount_limit:
            reasons.append("UPI_LIMIT_EXCEEDED")
        if config.bank_level_enforcement and (
            bank_count > config.bank_count_limit or bank_amount > config.bank_amount_limit
        ):
            reasons.append("BANK_LIMIT_EXCEEDED")
        return RollingCheck(
            allowed=not reasons,
            blocking_reasons=tuple(reasons),
            upi_count_after=upi_count,
            bank_count_after=bank_count,
            upi_amount_after=upi_amount,
            bank_amount_after=bank_amount,
        )

    def reserve(
        self,
        *,
        event_id: str,
        upi: UPIInput,
        amount: Decimal,
        at: datetime,
        config: PlannerConfig,
    ) -> "RollingLimitTracker":
        if any(event.id == event_id for event in self.events):
            raise ValueError("Application event ID already exists")
        result = self.check(upi=upi, amount=amount, at=at, config=config)
        if not result.allowed:
            raise ValueError(f"Rolling limit exceeded: {', '.join(result.blocking_reasons)}")
        event = RollingUsageInput(
            id=event_id,
            bank_id=upi.bank_id,
            upi_id=upi.id,
            amount=amount,
            submitted_at=at,
            cancelled=False,
        )
        return RollingLimitTracker((*self.events, event))
