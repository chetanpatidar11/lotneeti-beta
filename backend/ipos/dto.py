"""Canonical, ORM-free IPO records shared by source adapters."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol


def _date(value: object) -> date:
    if isinstance(value, datetime):
        raise ValueError("Use a date without a time")
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


@dataclass(frozen=True)
class IPORecord:
    source_key: str
    source_record_id: str
    issuer_name: str
    issue_type: str
    lower_price: Decimal
    upper_price: Decimal
    lot_size: int
    open_date: date
    close_date: date
    allotment_date: date
    listing_date: date | None
    symbol: str
    status: str
    publication_state: str
    source_url: str
    source_observed_at: datetime
    provided_fields: tuple[str, ...]

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, object],
        *,
        source_key: str,
        source_record_id: str,
        observed_at: datetime,
    ) -> "IPORecord":
        if not source_key or not source_record_id:
            raise ValueError("Source identity is required")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("Source observation time must have a timezone")
        return cls(
            source_key=source_key,
            source_record_id=source_record_id,
            issuer_name=str(raw["issuer_name"]).strip(),
            issue_type=str(raw["issue_type"]),
            lower_price=Decimal(str(raw["lower_price"])),
            upper_price=Decimal(str(raw["upper_price"])),
            lot_size=int(raw["lot_size"]),
            open_date=_date(raw["open_date"]),
            close_date=_date(raw["close_date"]),
            allotment_date=_date(raw["allotment_date"]),
            listing_date=_date(raw["listing_date"]) if raw.get("listing_date") else None,
            symbol=str(raw.get("symbol") or "").strip(),
            status=str(raw.get("status") or "UPCOMING"),
            publication_state=str(raw.get("publication_state") or "DRAFT"),
            source_url=str(raw.get("source_url") or ""),
            source_observed_at=observed_at.astimezone(UTC),
            provided_fields=tuple(sorted(raw)),
        )

    def payload(self) -> dict[str, object]:
        return {
            "source_key": self.source_key,
            "source_record_id": self.source_record_id,
            "issuer_name": self.issuer_name,
            "symbol": self.symbol,
            "issue_type": self.issue_type,
            "lower_price": str(self.lower_price),
            "upper_price": str(self.upper_price),
            "lot_size": self.lot_size,
            "open_date": self.open_date.isoformat(),
            "close_date": self.close_date.isoformat(),
            "allotment_date": self.allotment_date.isoformat(),
            "listing_date": self.listing_date.isoformat() if self.listing_date else None,
            "status": self.status,
            "publication_state": self.publication_state,
            "source_url": self.source_url,
            "provided_fields": list(self.provided_fields),
        }

    @property
    def payload_hash(self) -> str:
        encoded = json.dumps(self.payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def model_fields(self) -> dict[str, object]:
        payload = self.payload()
        payload.pop("provided_fields")
        return {
            **payload,
            "lower_price": self.lower_price,
            "upper_price": self.upper_price,
            "open_date": self.open_date,
            "close_date": self.close_date,
            "allotment_date": self.allotment_date,
            "listing_date": self.listing_date,
            "source_observed_at": self.source_observed_at,
            "source_payload_hash": self.payload_hash,
        }


class IPOProvider(Protocol):
    key: str

    def normalize(
        self, raw: Mapping[str, object], *, source_record_id: str, observed_at: datetime
    ) -> IPORecord: ...
