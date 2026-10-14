"""One IPO per file, in the broker workbook's column order."""

import csv
from io import StringIO

from exports.adapters import ExportRow
from exports.generic_csv import _cell


class DematCSVAdapter:
    format_id = "demat_csv"
    version = "v1"
    content_type = "text/csv; charset=utf-8"
    extension = "csv"
    columns = ("Name", "PAN", "Type", "DPID", "CLIENT ID", "UPI ID", "Account Number", "Bank Name")

    def render(self, rows: tuple[ExportRow, ...]) -> bytes:
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(self.columns)
        for row in rows:
            writer.writerow(
                tuple(
                    _cell(value)
                    for value in (
                        row.applicant_name,
                        row.pan,
                        row.depository,
                        "" if row.depository == "CDSL" else row.dp_id,
                        row.client_id,
                        row.upi_handle,
                        "",
                        "",
                    )
                )
            )
        return output.getvalue().encode("utf-8")
