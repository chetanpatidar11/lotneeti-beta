import csv
from io import StringIO

from test_export_adapters import sample_row

from exports.adapters import ExportRegistry
from exports.generic_csv import GenericCSVAdapter


def test_generic_csv_is_deterministic_and_contains_exact_mapping():
    registry = ExportRegistry((GenericCSVAdapter(),))
    rows = (sample_row(2), sample_row(1))
    first = registry.render("generic_csv", rows)
    second = registry.render("generic_csv", tuple(reversed(rows)))
    assert first == second
    assert first.format_version == "v1"
    assert first.content_type == "text/csv; charset=utf-8"
    assert first.data.endswith(b"\n")
    parsed = list(csv.reader(StringIO(first.data.decode("utf-8"))))
    assert parsed[0] == list(GenericCSVAdapter.columns)
    assert parsed[1] == [
        "synthetic-ipo",
        "Synthetic Industries",
        "synthetic-1",
        "Synthetic Investor",
        "TESTX0001A",
        "RETAIL",
        "1",
        "15000.00",
        "CDSL",
        "DEMO-DP-001",
        "DEMO-CLIENT-001",
        "Synthetic Bank",
        "DEMO-ACCOUNT-001",
        "demo@upi.test",
    ]
    assert parsed[2][2] == "synthetic-2"


def test_generic_csv_quotes_commas_and_neutralizes_spreadsheet_formula():
    from dataclasses import replace

    row = replace(sample_row(1), applicant_name="=SUM(1,2)", bank_name="Demo, Bank")
    data = GenericCSVAdapter().render((row,)).decode("utf-8")
    parsed = list(csv.reader(StringIO(data)))
    assert parsed[1][3] == "'=SUM(1,2)"
    assert parsed[1][11] == "Demo, Bank"
