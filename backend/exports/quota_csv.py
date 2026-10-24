"""Explicit categories and funding methods for mixed quota plans."""

import csv
from io import StringIO

from exports.generic_csv import _cell


class QuotaCSVAdapter:
    format_id = "quota_csv"
    version = "v1"
    content_type = "text/csv; charset=utf-8"
    extension = "csv"
    columns = (
        "IPO",
        "Name",
        "PAN",
        "Category",
        "Lots",
        "Amount",
        "Funding method",
        "Depository",
        "DPID",
        "Client ID",
        "Bank name",
        "Bank account",
        "UPI ID",
    )

    def render(self, rows):
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(self.columns)
        labels = {"RETAIL": "Retail", "SHNI": "sHNI", "SHARE": "Shareholder", "BHNI": "bHNI"}
        for row in rows:
            writer.writerow(
                _cell(value)
                for value in (
                    row.ipo_name,
                    row.applicant_name,
                    row.pan,
                    labels[row.category],
                    row.lots,
                    format(row.amount, ".2f"),
                    "Bank ASBA" if row.category == "BHNI" else "UPI",
                    row.depository,
                    row.dp_id,
                    row.client_id,
                    row.bank_name,
                    row.bank_account_number,
                    row.upi_handle,
                )
            )
        return output.getvalue().encode("utf-8")
