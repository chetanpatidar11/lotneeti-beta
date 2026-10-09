"""Stable generic CSV for an authorized plan export."""

import csv
from io import StringIO

from exports.adapters import ExportRow


def _cell(value: object) -> str:
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


class GenericCSVAdapter:
    format_id = "generic_csv"
    version = "v1"
    content_type = "text/csv; charset=utf-8"
    extension = "csv"
    columns = (
        "IPO ID",
        "IPO Name",
        "Applicant ID",
        "Applicant Name",
        "PAN",
        "Category",
        "Lots",
        "Amount INR",
        "Depository",
        "DP ID",
        "Client ID",
        "Bank",
        "Bank Account",
        "UPI ID",
    )

    def render(self, rows: tuple[ExportRow, ...]) -> bytes:
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(self.columns)
        for row in rows:
            writer.writerow(
                _cell(value)
                for value in (
                    row.ipo_id,
                    row.ipo_name,
                    row.applicant_id,
                    row.applicant_name,
                    row.pan,
                    row.category,
                    row.lots,
                    f"{row.amount:.2f}",
                    row.depository,
                    row.dp_id,
                    row.client_id,
                    row.bank_name,
                    row.bank_account_number,
                    row.upi_handle,
                )
            )
        return output.getvalue().encode("utf-8")
