import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree

from django.db import transaction
from django.utils import timezone

from core.audit import record_event
from core.crypto import decrypt_value, encrypt_value
from funding.models import (
    BalanceChange,
    BankAccount,
    UPIHandle,
    account_hash_for_workspace,
    upi_hash_for_workspace,
)
from investors.models import (
    AccountImportBatch,
    DematAccount,
    Investor,
    pan_hash_for_workspace,
)

MAX_WORKBOOK_BYTES = 5 * 1024 * 1024
MAX_XML_BYTES = 20 * 1024 * 1024
EXPECTED_HEADERS = (
    "Name",
    "PAN",
    "Type",
    "DPID",
    "CLIENT ID",
    "UPI ID",
    "Account Number",
    "Bank Name",
)
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
UPI_PATTERN = re.compile(r"^[a-z0-9._-]+@[a-z0-9._-]+$")
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class AccountImportError(ValueError):
    def __init__(self, message, *, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _tag(name: str) -> str:
    return f"{{{MAIN_NS}}}{name}"


def _column_number(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    if not letters:
        raise AccountImportError("The workbook contains an invalid cell reference.")
    number = 0
    for letter in letters.group(0):
        number = number * 26 + ord(letter) - ord("A") + 1
    return number


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = _read_xml(archive, "xl/sharedStrings.xml")
    except KeyError:
        return []
    values = []
    for item in root.findall(_tag("si")):
        values.append("".join(node.text or "" for node in item.iter(_tag("t"))))
    return values


def _read_xml(archive: zipfile.ZipFile, path: str):
    with archive.open(path) as part:
        data = part.read(MAX_XML_BYTES + 1)
    if len(data) > MAX_XML_BYTES:
        raise AccountImportError("The workbook contains an oversized sheet or string table.")
    return ElementTree.fromstring(data)


def _sheet_path(archive: zipfile.ZipFile) -> str:
    workbook = _read_xml(archive, "xl/workbook.xml")
    sheets = workbook.find(_tag("sheets"))
    if sheets is None or len(sheets) != 1:
        raise AccountImportError("Use a workbook with exactly one account sheet.")
    relationship_id = sheets[0].attrib.get(f"{{{REL_NS}}}id")
    relationships = _read_xml(archive, "xl/_rels/workbook.xml.rels")
    for relationship in relationships:
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib["Target"].lstrip("/")
            return str(PurePosixPath("xl") / target.removeprefix("xl/"))
    raise AccountImportError("The workbook sheet relationship is invalid.")


def _cell_value(cell, shared: list[str]) -> str:
    if cell.find(_tag("f")) is not None:
        raise AccountImportError("Formula cells are not accepted in an account import workbook.")
    raw = cell.find(_tag("v"))
    value = "" if raw is None or raw.text is None else raw.text
    if cell.attrib.get("t") == "s":
        try:
            return shared[int(value)]
        except (IndexError, ValueError) as exc:
            raise AccountImportError(
                "The workbook contains an invalid shared-string cell."
            ) from exc
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(_tag("t")))
    return value


def _read_rows(workbook_bytes: bytes) -> list[dict[str, str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as archive:
            names = set(archive.namelist())
            if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
                raise AccountImportError("This is not a valid .xlsx workbook.")
            shared = _shared_strings(archive)
            root = _read_xml(archive, _sheet_path(archive))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise AccountImportError("This is not a valid .xlsx workbook.") from exc

    rows = []
    seen_row_numbers = set()
    for row in root.iter(_tag("row")):
        values = {}
        for cell in row.findall(_tag("c")):
            column = _column_number(cell.attrib.get("r", ""))
            value = _cell_value(cell, shared)
            if column > len(EXPECTED_HEADERS) and value.strip():
                raise AccountImportError(
                    "The account workbook has values outside columns A through H."
                )
            values[column] = value
        if any(value.strip() for value in values.values()):
            try:
                row_number = int(row.attrib.get("r", len(rows) + 1))
            except ValueError as exc:
                raise AccountImportError("The workbook contains an invalid row number.") from exc
            if row_number < 1 or row_number in seen_row_numbers:
                raise AccountImportError("The workbook contains a duplicate or invalid row number.")
            seen_row_numbers.add(row_number)
            rows.append({"row_number": row_number, "values": values})
    if not rows:
        raise AccountImportError("The workbook has no rows.")
    if rows[0]["row_number"] != 1:
        raise AccountImportError("The approved column headers must be in row 1.")
    headers = tuple(rows[0]["values"].get(index, "").strip() for index in range(1, 9))
    if headers != EXPECTED_HEADERS:
        raise AccountImportError(
            "Use the approved AccountImportTemplate.xlsx column order: "
            + ", ".join(EXPECTED_HEADERS)
        )
    return [
        {
            "row_number": row["row_number"],
            **{
                header: row["values"].get(index, "").strip()
                for index, header in enumerate(EXPECTED_HEADERS, start=1)
            },
        }
        for row in rows[1:]
    ]


def _validate_row(row: dict[str, str]) -> list[str]:
    errors = []
    if not row["Name"]:
        errors.append("Name is required.")
    elif len(row["Name"]) > 120:
        errors.append("Name is too long.")
    pan = row["PAN"].upper()
    if not PAN_PATTERN.fullmatch(pan):
        errors.append("PAN must use the ten-character format ABCDE1234F.")
    row["PAN"] = pan
    row["Type"] = row["Type"].upper()
    if row["Type"] not in {"CDSL", "NSDL"}:
        errors.append("Type must be CDSL or NSDL.")
    if row["Type"] == "NSDL" and not row["DPID"]:
        errors.append("DPID is required for NSDL rows.")
    if not row["CLIENT ID"]:
        errors.append("CLIENT ID is required.")
    upi = row["UPI ID"].lower()
    if not UPI_PATTERN.fullmatch(upi):
        errors.append("UPI ID must look like name@provider.")
    row["UPI ID"] = upi
    if not row["Account Number"]:
        errors.append("Account Number is required.")
    if not row["Bank Name"]:
        errors.append("Bank Name is required.")
    return errors


def parse_workbook(uploaded_file) -> tuple[str, list[dict[str, str]]]:
    if not uploaded_file.name.lower().endswith(".xlsx"):
        raise AccountImportError("Upload an .xlsx workbook.")
    if uploaded_file.size > MAX_WORKBOOK_BYTES:
        raise AccountImportError("The workbook must be 5 MB or smaller.")
    uploaded_file.seek(0)
    data = uploaded_file.read(MAX_WORKBOOK_BYTES + 1)
    if len(data) > MAX_WORKBOOK_BYTES:
        raise AccountImportError("The workbook must be 5 MB or smaller.")
    rows = _read_rows(data)
    pan_counts = {}
    for row in rows:
        row["errors"] = _validate_row(row)
        if PAN_PATTERN.fullmatch(row["PAN"]):
            pan_counts[row["PAN"]] = pan_counts.get(row["PAN"], 0) + 1
    for row in rows:
        if pan_counts.get(row["PAN"], 0) > 1:
            row["errors"].append("PAN appears more than once in this workbook.")
    return hashlib.sha256(data).hexdigest(), rows


def _mask(value: str, prefix: str = "••••") -> str:
    return f"{prefix}{value[-4:]}" if value else "—"


def _masked_upi(value: str) -> str:
    return f"••••@{value.rsplit('@', 1)[1]}" if "@" in value else "—"


def preview_payload(batch: AccountImportBatch) -> dict:
    rows = json.loads(decrypt_value(batch.rows_ciphertext, purpose="account-import"))
    return {
        "id": str(batch.pk),
        "status": batch.status,
        "source_filename": batch.source_filename,
        "row_count": batch.row_count,
        "error_count": batch.error_count,
        "rows": [
            {
                "row_number": row["row_number"],
                "name": row["Name"],
                "pan_masked": _mask(row["PAN"], prefix="******"),
                "type": row["Type"],
                "dpid_masked": _mask(row["DPID"]),
                "client_id_masked": _mask(row["CLIENT ID"]),
                "upi_masked": _masked_upi(row["UPI ID"]),
                "account_masked": _mask(row["Account Number"]),
                "bank_name": row["Bank Name"],
                "errors": row["errors"],
            }
            for row in rows
        ],
    }


def create_preview(*, workspace, actor, uploaded_file) -> AccountImportBatch:
    source_hash, rows = parse_workbook(uploaded_file)
    for row in rows:
        if (
            PAN_PATTERN.fullmatch(row["PAN"])
            and Investor.objects.filter(
                workspace=workspace,
                pan_lookup_hash=pan_hash_for_workspace(workspace.pk, row["PAN"]),
            ).exists()
        ):
            row["errors"].append("PAN already belongs to an investor in this workspace.")
    batch = AccountImportBatch.objects.create(
        workspace=workspace,
        created_by=actor,
        source_filename=uploaded_file.name[:255],
        source_hash=source_hash,
        rows_ciphertext=encrypt_value(json.dumps(rows), purpose="account-import"),
        row_count=len(rows),
        error_count=sum(bool(row["errors"]) for row in rows),
    )
    record_event(
        action="account_import.previewed",
        target=batch,
        actor=actor,
        workspace=workspace,
        metadata={"row_count": batch.row_count, "error_count": batch.error_count},
    )
    return batch


def _find_or_create_demat(investor, row):
    for demat in DematAccount.objects.filter(investor=investor):
        if (
            demat.depository == row["Type"]
            and decrypt_value(demat.dp_id_ciphertext, purpose="demat") == row["DPID"]
            and decrypt_value(demat.client_id_ciphertext, purpose="demat") == row["CLIENT ID"]
        ):
            return demat, False
    demat = DematAccount(investor=investor, depository=row["Type"])
    demat.set_dp_id(row["DPID"])
    demat.set_client_id(row["CLIENT ID"])
    demat.save()
    return demat, True


@transaction.atomic
def confirm_batch(*, batch: AccountImportBatch, actor, row_numbers: list[int] | None) -> dict:
    batch = AccountImportBatch.objects.select_for_update().get(pk=batch.pk)
    if batch.status != AccountImportBatch.Status.PREVIEWED:
        raise AccountImportError("This import preview has already been confirmed.")
    rows = json.loads(decrypt_value(batch.rows_ciphertext, purpose="account-import"))
    selected_numbers = {row["row_number"] for row in rows if not row["errors"]}
    if row_numbers is not None:
        selected_numbers = set(row_numbers)
        unknown = selected_numbers - {row["row_number"] for row in rows}
        if unknown:
            raise AccountImportError("Select only rows shown in this import preview.")
    invalid = {
        str(row["row_number"]): row["errors"]
        for row in rows
        if row["row_number"] in selected_numbers and row["errors"]
    }
    if invalid:
        raise AccountImportError("Remove rows with errors before confirming.", errors=invalid)
    selected = [row for row in rows if row["row_number"] in selected_numbers]
    if not selected:
        raise AccountImportError("Select at least one valid row to import.")

    seen_pans = set()
    for row in selected:
        if row["PAN"] in seen_pans:
            raise AccountImportError(
                "Each import row must have a different PAN.",
                errors={str(row["row_number"]): ["PAN appears more than once."]},
            )
        seen_pans.add(row["PAN"])
        if Investor.objects.filter(
            workspace=batch.workspace,
            pan_lookup_hash=pan_hash_for_workspace(batch.workspace_id, row["PAN"]),
        ).exists():
            raise AccountImportError(
                "This PAN already belongs to an investor in this workspace.",
                errors={str(row["row_number"]): ["PAN already exists."]},
            )

    created = {"investors": 0, "demats": 0, "banks": 0, "upis": 0}
    next_priority = (
        Investor.objects.filter(workspace=batch.workspace)
        .order_by("-planning_priority")
        .values_list("planning_priority", flat=True)
        .first()
        or 0
    ) + 1
    for row in selected:
        investor = Investor(
            workspace=batch.workspace,
            name=row["Name"],
            planning_priority=next_priority,
        )
        investor.set_pan(row["PAN"])
        investor.save()
        next_priority += 1
        created["investors"] += 1

        _demat, was_created = _find_or_create_demat(investor, row)
        created["demats"] += was_created

        bank = BankAccount.objects.filter(
            workspace=batch.workspace,
            account_lookup_hash=account_hash_for_workspace(
                batch.workspace_id, row["Account Number"]
            ),
        ).first()
        if bank is None:
            bank = BankAccount(
                workspace=batch.workspace,
                owner=investor,
                bank_name=row["Bank Name"],
                current_balance=0,
            )
            bank.set_account_number(row["Account Number"])
            bank.save()
            BalanceChange.objects.create(
                bank=bank,
                operation=BalanceChange.Operation.SET,
                old_balance=0,
                delta=0,
                new_balance=0,
                actor=actor,
                note="Imported account; set the current Balance before planning.",
            )
            created["banks"] += 1
        elif bank.owner_id != investor.pk:
            raise AccountImportError(
                "An account number is already linked to another investor.",
                errors={str(row["row_number"]): ["Bank account owner conflict."]},
            )

        upi_hash = upi_hash_for_workspace(batch.workspace_id, row["UPI ID"])
        upi = UPIHandle.objects.filter(handle_lookup_hash=upi_hash).first()
        if upi is None:
            upi = UPIHandle(bank=bank, holder=investor, verified=False)
            upi.set_handle(row["UPI ID"])
            upi.save()
            created["upis"] += 1
        elif upi.bank_id != bank.pk or upi.holder_id != investor.pk:
            raise AccountImportError(
                "A UPI ID is already linked to another account.",
                errors={str(row["row_number"]): ["UPI ownership conflict."]},
            )

    batch.status = AccountImportBatch.Status.CONFIRMED
    batch.confirmed_at = timezone.now()
    batch.save(update_fields=["status", "confirmed_at"])
    record_event(
        action="account_import.confirmed",
        target=batch,
        actor=actor,
        workspace=batch.workspace,
        metadata={"row_count": len(selected), "entity_counts": created},
    )
    return {"status": batch.status, "imported_rows": len(selected), "created": created}
