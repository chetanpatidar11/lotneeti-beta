from decimal import Decimal

import pytest

from exports.adapters import ExportRegistry, ExportRow


class SyntheticAdapter:
    format_id = "synthetic"
    version = "v1"
    content_type = "text/plain"
    extension = "txt"

    def render(self, rows: tuple[ExportRow, ...]) -> bytes:
        return "\n".join(f"{row.position}:{row.applicant_id}" for row in rows).encode()


def sample_row(position: int) -> ExportRow:
    return ExportRow(
        position=position,
        ipo_id="synthetic-ipo",
        ipo_name="Synthetic Industries",
        applicant_id=f"synthetic-{position}",
        applicant_name="Synthetic Investor",
        pan="TESTX0001A",
        category="RETAIL",
        lots=1,
        amount=Decimal("15000.00"),
        depository="CDSL",
        dp_id="DEMO-DP-001",
        client_id="DEMO-CLIENT-001",
        bank_name="Synthetic Bank",
        bank_account_number="DEMO-ACCOUNT-001",
        upi_handle="demo@upi.test",
    )


def test_named_versioned_adapter_maps_rows_in_plan_order():
    registry = ExportRegistry((SyntheticAdapter(),))
    assert registry.formats() == (("synthetic", "v1"),)
    artifact = registry.render("synthetic", (sample_row(2), sample_row(1)))
    assert artifact.format_id == "synthetic"
    assert artifact.format_version == "v1"
    assert artifact.content_type == "text/plain"
    assert artifact.extension == "txt"
    assert artifact.data == b"1:synthetic-1\n2:synthetic-2"


def test_adapter_registry_rejects_duplicate_or_unknown_format():
    with pytest.raises(ValueError, match="Duplicate export format"):
        ExportRegistry((SyntheticAdapter(), SyntheticAdapter()))
    with pytest.raises(ValueError, match="Unknown export format"):
        ExportRegistry((SyntheticAdapter(),)).render("missing", ())
