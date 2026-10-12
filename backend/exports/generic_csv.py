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
    version = "v2"
    content_type = "text/csv; charset=utf-8"
    extension = "csv"
    columns = (
        "Name",
        "PAN",
        "Depository",
        "Priority",
        "Client ID",
        "UPI ID for IPO",
        "Bank account no.",
    )

    def render(self, rows: tuple[ExportRow, ...]) -> bytes:
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(self.columns)
        for row in rows:
            writer.writerow(
                _cell(value)
                for value in (
                    row.applicant_name,
                    row.pan,
                    row.depository,
                    row.priority,
                    row.client_id,
                    row.upi_handle,
                    row.bank_account_number,
                )
            )
        return output.getvalue().encode("utf-8")
