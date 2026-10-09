"""Keep file formats separate from planner and storage concerns."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExportRow:
    position: int
    ipo_id: str
    ipo_name: str
    applicant_id: str
    applicant_name: str
    pan: str
    category: str
    lots: int
    amount: Decimal
    depository: str
    dp_id: str
    client_id: str
    bank_name: str
    bank_account_number: str
    upi_handle: str


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    format_id: str
    format_version: str
    content_type: str
    extension: str
    data: bytes


class ExportAdapter(Protocol):
    format_id: str
    version: str
    content_type: str
    extension: str

    def render(self, rows: tuple[ExportRow, ...]) -> bytes: ...


class ExportRegistry:
    def __init__(self, adapters: tuple[ExportAdapter, ...]):
        self._adapters: dict[str, ExportAdapter] = {}
        for adapter in adapters:
            if not all(
                isinstance(getattr(adapter, field, None), str) and getattr(adapter, field)
                for field in ("format_id", "version", "content_type", "extension")
            ):
                raise ValueError("Export adapter metadata must be complete")
            if adapter.format_id in self._adapters:
                raise ValueError(f"Duplicate export format: {adapter.format_id}")
            self._adapters[adapter.format_id] = adapter

    def formats(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted((adapter.format_id, adapter.version) for adapter in self._adapters.values())
        )

    def render(self, format_id: str, rows: tuple[ExportRow, ...]) -> ExportArtifact:
        try:
            adapter = self._adapters[format_id]
        except KeyError as exc:
            raise ValueError(f"Unknown export format: {format_id}") from exc
        data = adapter.render(tuple(sorted(rows, key=lambda row: row.position)))
        return ExportArtifact(
            format_id=adapter.format_id,
            format_version=adapter.version,
            content_type=adapter.content_type,
            extension=adapter.extension,
            data=data,
        )
