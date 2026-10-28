import io
import json
import re
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import BalanceChange, BankAccount, UPIHandle
from investors.models import AccountImportBatch, DematAccount, Investor
from investors.tasks import purge_expired_account_import_previews

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples" / "AccountImportTemplate.xlsx"


def upload():
    return SimpleUploadedFile(
        "AccountImportTemplate.xlsx",
        SAMPLE.read_bytes(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def invalid_pan_upload():
    source = SAMPLE.read_bytes()
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(source)) as source_zip,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as output_zip,
    ):
        for name in source_zip.namelist():
            contents = source_zip.read(name)
            if name == "xl/sharedStrings.xml":
                contents = contents.replace(b"ABCDE1234F", b"BADPA00000")
            if name == "xl/worksheets/sheet1.xml":
                contents = contents.replace(
                    b'<c r="B3" t="s"><v>8</v></c>',
                    b'<c r="B3" t="inlineStr"><is><t>ABCDE5678G</t></is></c>',
                )
            output_zip.writestr(name, contents)
    return SimpleUploadedFile(
        "AccountImportTemplate.xlsx",
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def edited_upload(part_name, old, new):
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(SAMPLE.read_bytes())) as source_zip,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as output_zip,
    ):
        for name in source_zip.namelist():
            contents = source_zip.read(name)
            if name == part_name:
                assert old in contents
                contents = contents.replace(old, new, 1)
            output_zip.writestr(name, contents)
    return SimpleUploadedFile("AccountImportTemplate.xlsx", output.getvalue())


def distinct_rows_upload():
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(SAMPLE.read_bytes())) as source_zip,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as output_zip,
    ):
        for name in source_zip.namelist():
            contents = source_zip.read(name)
            if name == "xl/worksheets/sheet1.xml":
                contents = (
                    contents.replace(
                        b'<c r="B3" t="s"><v>8</v></c>',
                        b'<c r="B3" t="inlineStr"><is><t>FGHIJ5678K</t></is></c>',
                    )
                    .replace(
                        b'<c r="F3" t="s"><v>10</v></c>',
                        b'<c r="F3" t="inlineStr"><is><t>other@upi</t></is></c>',
                    )
                    .replace(
                        b'<c r="G3"><v>123456789</v></c>',
                        b'<c r="G3"><v>987654321</v></c>',
                    )
                )
            output_zip.writestr(name, contents)
    return SimpleUploadedFile("DistinctAccounts.xlsx", output.getvalue())


def optional_columns_upload(*, keep: str):
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(distinct_rows_upload().read())) as source_zip,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as output_zip,
    ):
        for name in source_zip.namelist():
            contents = source_zip.read(name)
            if name == "xl/worksheets/sheet1.xml":
                if keep == "bank":
                    contents = re.sub(rb'<c r="G([1-3])"[^>]*>.*?</c>', b"", contents)
                    contents = contents.replace(
                        b'<c r="H1" t="s"><v>7</v></c>',
                        b'<c r="G1" t="inlineStr"><is><t>Bank Name</t></is></c>',
                    )
                    contents = contents.replace(b'r="H2"', b'r="G2"')
                    contents = contents.replace(b'r="H3"', b'r="G3"')
                else:
                    columns = b"[GH]" if keep == "neither" else b"H"
                    contents = re.sub(rb'<c r="' + columns + rb'[1-3]"[^>]*>.*?</c>', b"", contents)
            output_zip.writestr(name, contents)
    return SimpleUploadedFile("OptionalBankColumns.xlsx", output.getvalue())


def missing_bank_upload():
    source = distinct_rows_upload().read()
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(source)) as source_zip,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as output_zip,
    ):
        for name in source_zip.namelist():
            contents = source_zip.read(name)
            if name == "xl/worksheets/sheet1.xml":
                contents = contents.replace(b'<c r="G2"><v>123456789</v></c>', b"")
                contents = contents.replace(b'<c r="H2" t="s"><v>11</v></c>', b"")
            output_zip.writestr(name, contents)
    return SimpleUploadedFile("MissingBank.xlsx", output.getvalue())


def partial_bank_upload(*, missing: str):
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(distinct_rows_upload().read())) as source_zip,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as output_zip,
    ):
        for name in source_zip.namelist():
            contents = source_zip.read(name)
            if name == "xl/worksheets/sheet1.xml":
                if missing == "account":
                    contents = contents.replace(b'<c r="G2"><v>123456789</v></c>', b"")
                else:
                    contents = contents.replace(b'<c r="H2" t="s"><v>11</v></c>', b"")
            output_zip.writestr(name, contents)
    return SimpleUploadedFile("PartialBank.xlsx", output.getvalue())


def shared_upi_without_banks_upload():
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(distinct_rows_upload().read())) as source_zip,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as output_zip,
    ):
        for name in source_zip.namelist():
            contents = source_zip.read(name)
            if name == "xl/worksheets/sheet1.xml":
                contents = contents.replace(
                    b'<c r="F3" t="inlineStr"><is><t>other@upi</t></is></c>',
                    b'<c r="F3" t="inlineStr"><is><t>somename@upi</t></is></c>',
                )
                for row, number in ((b"2", b"123456789"), (b"3", b"987654321")):
                    contents = contents.replace(
                        b'<c r="G' + row + b'"><v>' + number + b"</v></c>", b""
                    )
                    contents = contents.replace(b'<c r="H' + row + b'" t="s"><v>11</v></c>', b"")
            output_zip.writestr(name, contents)
    return SimpleUploadedFile("SharedUPI.xlsx", output.getvalue())


def seventeen_rows_six_upis_upload(count=17):
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(SAMPLE.read_bytes())) as source_zip,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as output_zip,
    ):
        for name in source_zip.namelist():
            contents = source_zip.read(name)
            if name == "xl/worksheets/sheet1.xml":
                header = re.search(rb'<row r="1".*?</row>', contents)
                assert header is not None
                rows = []
                for index in range(count):
                    row_number = index + 2
                    cells = {
                        "A": f"Person {index + 1}",
                        "B": f"ABCDE{index:04d}F",
                        "C": "CDSL",
                        "E": f"{10000000 + index}",
                        "F": f"group{index % 6}@upi",
                    }
                    cell_xml = "".join(
                        f'<c r="{column}{row_number}" t="inlineStr"><is><t>{value}</t></is></c>'
                        for column, value in cells.items()
                    )
                    rows.append(f'<row r="{row_number}">{cell_xml}</row>')
                contents = re.sub(
                    rb"<sheetData>.*?</sheetData>",
                    b"<sheetData>" + header.group() + "".join(rows).encode() + b"</sheetData>",
                    contents,
                )
            output_zip.writestr(name, contents)
    return SimpleUploadedFile("SeventeenDemats.xlsx", output.getvalue())


@pytest.mark.django_db
def test_sample_account_workbook_previews_authorized_ids_and_confirms_only_selected_rows():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)

    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": distinct_rows_upload()},
        format="multipart",
    )
    assert preview.status_code == 201
    assert preview.data["row_count"] == 2
    assert preview.data["error_count"] == 0
    assert preview.data["rows"][0]["pan_masked"] == "******234F"
    assert preview.data["rows"][0]["pan_display"] == "ABCDE1234F"
    assert preview.data["rows"][0]["client_id_display"]
    assert preview.data["rows"][0]["account_masked"] == "••••6789"

    batch = AccountImportBatch.objects.get(pk=preview.data["id"])
    assert "ABCDE1234F" not in batch.rows_ciphertext
    viewer = User.objects.create_user(email="viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    masked = client.get(reverse("account-import-preview", args=[workspace.pk, batch.pk]))
    assert masked.data["rows"][0]["pan_display"] == "ABCDE1234F"
    assert (
        masked.data["rows"][0]["client_id_display"] == preview.data["rows"][0]["client_id_display"]
    )
    assert masked.data["rows"][0]["account_display"] == "123456789"
    client.force_authenticate(owner)
    confirmed = client.post(
        reverse("account-import-preview", args=[workspace.pk, batch.pk]),
        {"row_numbers": [2]},
        format="json",
    )
    assert confirmed.status_code == 200
    assert confirmed.data["imported_rows"] == 1
    assert confirmed.data["created"] == {
        "investors": 1,
        "demats": 1,
        "banks": 1,
        "upis": 1,
        "payment_pending": 0,
    }
    assert Investor.objects.count() == 1
    assert DematAccount.objects.count() == 1
    assert BankAccount.objects.count() == 1
    assert UPIHandle.objects.count() == 1
    assert AuditEvent.objects.filter(action="account_import.confirmed").exists()
    batch.refresh_from_db()
    assert batch.rows_ciphertext == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("keep", "bank_name", "reference"),
    [("neither", "BANK", True), ("account", "BANK", False), ("bank", "HDFC Bank", True)],
)
def test_workbook_optional_bank_columns_import_without_errors(keep, bank_name, reference):
    owner = User.objects.create_user(email=f"{keep}@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": optional_columns_upload(keep=keep)},
        format="multipart",
    )
    assert preview.status_code == 201, preview.data
    assert preview.data["error_count"] == 0
    confirmed = client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {"row_numbers": [2]},
        format="json",
    )
    assert confirmed.status_code == 200, confirmed.data
    bank = BankAccount.objects.get()
    assert bank.bank_name == bank_name
    assert bank.is_imported_reference is reference
    assert bank.active and bank.current_balance == 0


@pytest.mark.django_db
def test_reviewed_image_rows_use_same_validation_and_import_flow():
    owner = User.objects.create_user(email="image-owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    rows = [
        {
            "Name": "Example Investor",
            "PAN": "ABCDE1234F",
            "Type": "CDSL",
            "DPID": "",
            "CLIENT ID": "12345678",
            "UPI ID": "example@upi",
        },
        {
            "Name": "Review This",
            "PAN": "BAD",
            "Type": "CDSL",
            "DPID": "",
            "CLIENT ID": "87654321",
            "UPI ID": "second@upi",
        },
    ]
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"source_filename": "accounts.png", "image_rows": json.dumps(rows)},
        format="multipart",
    )
    assert preview.status_code == 201, preview.data
    assert preview.data["row_count"] == 2
    assert preview.data["error_count"] == 1
    assert preview.data["rows"][0]["bank_name"] == "BANK"
    assert preview.data["rows"][0]["account_masked"] == "example@upi"
    confirmed = client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {"row_numbers": [2]},
        format="json",
    )
    assert confirmed.status_code == 200, confirmed.data
    assert Investor.objects.count() == 1
    assert BankAccount.objects.get().is_imported_reference


@pytest.mark.django_db
def test_image_rows_reject_oversized_fields_and_non_image_source():
    owner = User.objects.create_user(email="invalid-image@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    for filename, rows in (
        ("accounts.txt", [{"Name": "Example"}]),
        ("accounts.png", [{"Name": "x" * 501}]),
    ):
        response = client.post(
            reverse("account-import-list", args=[workspace.pk]),
            {"source_filename": filename, "image_rows": json.dumps(rows)},
            format="multipart",
        )
        assert response.status_code == 400
    assert not AccountImportBatch.objects.exists()


@pytest.mark.django_db
def test_old_import_previews_expire_and_legacy_confirmed_rows_are_scrubbed():
    owner = User.objects.create_user(email="cleanup@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    first = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": distinct_rows_upload()},
        format="multipart",
    )
    old = AccountImportBatch.objects.get(pk=first.data["id"])
    AccountImportBatch.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    second = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": distinct_rows_upload()},
        format="multipart",
    )
    legacy = AccountImportBatch.objects.get(pk=second.data["id"])
    legacy.status = AccountImportBatch.Status.CONFIRMED
    legacy.save(update_fields=["status"])

    result = purge_expired_account_import_previews()

    assert result == {"expired_previews": 1, "confirmed_scrubbed": 1}
    assert not AccountImportBatch.objects.filter(pk=old.pk).exists()
    legacy.refresh_from_db()
    assert legacy.rows_ciphertext == ""


@pytest.mark.django_db
def test_missing_bank_details_can_be_entered_for_a_selected_preview_row():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": missing_bank_upload()},
        format="multipart",
    )
    assert preview.status_code == 201
    assert preview.data["rows"][0]["errors"] == []
    assert preview.data["rows"][0]["payment_pending"] is False
    url = reverse("account-import-preview", args=[workspace.pk, preview.data["id"]])
    completed = client.post(
        url,
        {
            "row_numbers": [2],
            "bank_details": {
                "2": {
                    "account_number": "9876543210",
                    "bank_name": "Synthetic Bank",
                }
            },
        },
        format="json",
    )
    assert completed.status_code == 200
    assert completed.data["imported_rows"] == 1
    bank = BankAccount.objects.get()
    assert bank.bank_name == "Synthetic Bank"
    assert bank.account_masked == "••••3210"
    assert "9876543210" not in str(client.get(url).data)


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="WARN")
def test_shared_upi_requires_owner_then_creates_active_bank_with_zero_balance():
    from planner.snapshot_builder import build_snapshot

    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": shared_upi_without_banks_upload()},
        format="multipart",
    )
    assert preview.status_code == 201
    assert all(row["shared_upi"] for row in preview.data["rows"])
    assert all(row["bank_name"] == "BANK" for row in preview.data["rows"])
    assert all(row["account_masked"] == "somename@upi" for row in preview.data["rows"])
    url = reverse("account-import-preview", args=[workspace.pk, preview.data["id"]])
    missing_owner = client.post(url, {"row_numbers": [2, 3]}, format="json")
    assert missing_owner.status_code == 400
    assert Investor.objects.count() == 0

    result = client.post(
        url,
        {"row_numbers": [2, 3], "shared_upi_owners": {"somename@upi": 2}},
        format="json",
    )
    assert result.status_code == 200
    assert result.data["created"] == {
        "investors": 2,
        "demats": 2,
        "banks": 1,
        "upis": 1,
        "payment_pending": 0,
    }
    bank = BankAccount.objects.get()
    assert bank.bank_name == "BANK"
    assert bank.active is True
    assert bank.is_placeholder is False
    assert bank.is_imported_reference is True
    assert bank.current_balance == 0
    bank_detail = client.get(reverse("bank-detail", args=[workspace.pk, bank.pk]))
    assert bank_detail.data["account_number"] == "somename@upi"
    assert bank_detail.data["account_reference"] == "somename@upi"
    assert BalanceChange.objects.get(bank=bank).new_balance == 0
    assert UPIHandle.objects.get().verified is True
    assert all(investor.payment_ready for investor in Investor.objects.all())
    assert all(applicant.active for applicant in build_snapshot(workspace=workspace).applicants)
    assert (
        client.post(
            reverse("bank-set-balance", args=[workspace.pk, bank.pk]),
            {"amount": "1000.00"},
            format="json",
        ).status_code
        == 201
    )
    changed = client.patch(
        reverse("bank-detail", args=[workspace.pk, bank.pk]),
        {"bank_name": "Synthetic Bank", "account_number": "123400001111"},
        format="json",
    )
    assert changed.status_code == 200
    assert changed.data["is_imported_reference"] is False
    assert changed.data["account_reference"] == ""


@pytest.mark.django_db
def test_unique_upi_without_bank_fields_is_ready_after_import():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": missing_bank_upload()},
        format="multipart",
    )
    assert preview.status_code == 201
    assert preview.data["rows"][0]["payment_pending"] is False
    result = client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {"row_numbers": [2]},
        format="json",
    )
    assert result.status_code == 200
    assert result.data["created"]["payment_pending"] == 0
    bank = BankAccount.objects.get()
    assert bank.active and bank.is_imported_reference and bank.bank_name == "BANK"
    assert bank.current_balance == 0
    assert Investor.objects.get().payment_ready


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("missing", "expected_bank", "imported_reference"),
    [("account", "HDFC Bank", True), ("name", "BANK", False)],
)
def test_partial_bank_fields_use_defaults(missing, expected_bank, imported_reference):
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": partial_bank_upload(missing=missing)},
        format="multipart",
    )
    assert preview.status_code == 201
    assert preview.data["rows"][0]["errors"] == []
    result = client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {"row_numbers": [2]},
        format="json",
    )
    assert result.status_code == 200
    bank = BankAccount.objects.get()
    assert bank.bank_name == expected_bank
    assert bank.is_imported_reference is imported_reference
    assert bank.active and bank.current_balance == 0
    assert UPIHandle.objects.get().verified


@pytest.mark.django_db
def test_legacy_placeholder_can_be_activated_using_full_upi_reference():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": missing_bank_upload()},
        format="multipart",
    )
    client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {"row_numbers": [2]},
        format="json",
    )
    bank = BankAccount.objects.get()
    investor = Investor.objects.get()
    bank.bank_name = ""
    bank.active = False
    bank.is_placeholder = True
    bank.is_imported_reference = False
    bank.save()
    investor.payment_setup_pending = True
    investor.save()
    changed = client.patch(
        reverse("bank-detail", args=[workspace.pk, bank.pk]),
        {
            "owner": str(investor.pk),
            "bank_name": "BANK",
            "account_number": "somename@upi",
            "active": True,
        },
        format="json",
    )
    assert changed.status_code == 200
    bank.refresh_from_db()
    assert bank.active and not bank.is_placeholder and bank.is_imported_reference
    assert investor.payment_ready


@pytest.mark.django_db
def test_seventeen_demats_with_six_shared_upis_import_from_one_file():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": seventeen_rows_six_upis_upload()},
        format="multipart",
    )
    assert preview.status_code == 201
    assert preview.data["row_count"] == 17
    assert preview.data["error_count"] == 0
    response = client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {
            "row_numbers": list(range(2, 19)),
            "shared_upi_owners": {
                handle: next(
                    row["row_number"] for row in preview.data["rows"] if row["upi_id"] == handle
                )
                for handle in {row["upi_id"] for row in preview.data["rows"]}
                if sum(row["upi_id"] == handle for row in preview.data["rows"]) > 1
            },
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["created"] == {
        "investors": 17,
        "demats": 17,
        "banks": 6,
        "upis": 6,
        "payment_pending": 0,
    }
    assert DematAccount.objects.count() == 17
    assert BankAccount.objects.filter(active=True, is_imported_reference=True).count() == 6
    assert UPIHandle.objects.count() == 6
    first_investor = Investor.objects.order_by("planning_priority").first()
    duplicate_demat = client.post(
        reverse("demat-list", args=[workspace.pk, first_investor.pk]),
        {"depository": "CDSL", "client_id": "87654321"},
        format="json",
    )
    assert duplicate_demat.status_code == 400
    assert first_investor.demats.count() == 1
    existing_demat = first_investor.demats.get()
    edited_demat = client.patch(
        reverse("demat-detail", args=[workspace.pk, first_investor.pk, existing_demat.pk]),
        {"client_id": "87654321"},
        format="json",
    )
    assert edited_demat.status_code == 200
    assert first_investor.demats.count() == 1


@pytest.mark.django_db
def test_one_imported_investor_can_own_multiple_upis_outside_own_rows():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": seventeen_rows_six_upis_upload()},
        format="multipart",
    )
    assert preview.status_code == 201
    handles = {row["upi_id"] for row in preview.data["rows"]}
    result = client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {
            "row_numbers": list(range(2, 19)),
            "shared_upi_owners": {handle: "row:2" for handle in handles},
        },
        format="json",
    )
    assert result.status_code == 200
    assert result.data["created"]["banks"] == 6
    chosen_owner = Investor.objects.get(planning_priority=1)
    assert BankAccount.objects.filter(owner=chosen_owner).count() == 6
    assert UPIHandle.objects.filter(holder=chosen_owner).count() == 6
    assert all(investor.payment_ready for investor in Investor.objects.all())


@pytest.mark.django_db
def test_existing_active_workspace_investor_can_own_imported_shared_upi():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    existing = Investor(workspace=workspace, name="Existing Owner")
    existing.set_pan("UVWXY1234Z")
    existing.save()
    inactive = Investor(workspace=workspace, name="Inactive Owner", active=False)
    inactive.set_pan("PQRST1234U")
    inactive.save()
    other_workspace = create_workspace(name="Other Family", owner=owner)
    outsider = Investor(workspace=other_workspace, name="Outside Owner")
    outsider.set_pan("LMNOP5678Q")
    outsider.save()
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": shared_upi_without_banks_upload()},
        format="multipart",
    )
    url = reverse("account-import-preview", args=[workspace.pk, preview.data["id"]])
    for invalid_id in (outsider.pk, inactive.pk):
        rejected = client.post(
            url,
            {
                "row_numbers": [2, 3],
                "shared_upi_owners": {"somename@upi": f"investor:{invalid_id}"},
            },
            format="json",
        )
        assert rejected.status_code == 400
    assert Investor.objects.filter(workspace=workspace).count() == 2
    imported = client.post(
        url,
        {
            "row_numbers": [2, 3],
            "shared_upi_owners": {"somename@upi": f"investor:{existing.pk}"},
        },
        format="json",
    )
    assert imported.status_code == 200
    bank = BankAccount.objects.get(workspace=workspace)
    assert bank.owner_id == existing.pk
    assert UPIHandle.objects.get(bank=bank).holder_id == existing.pk


@pytest.mark.django_db
def test_import_bank_details_cannot_replace_workbook_values_or_bypass_other_errors():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": missing_bank_upload()},
        format="multipart",
    )
    url = reverse("account-import-preview", args=[workspace.pk, preview.data["id"]])
    replaced = client.post(
        url,
        {
            "row_numbers": [3],
            "bank_details": {
                "3": {
                    "account_number": "11111111",
                    "bank_name": "Other",
                }
            },
        },
        format="json",
    )
    assert replaced.status_code == 400
    assert Investor.objects.count() == 0
    unknown = client.post(
        url,
        {
            "row_numbers": [2],
            "bank_details": {
                "99": {
                    "account_number": "11111111",
                    "bank_name": "Other",
                }
            },
        },
        format="json",
    )
    assert unknown.status_code == 400
    assert Investor.objects.count() == 0


@pytest.mark.django_db
def test_sample_rows_with_same_pan_are_both_invalid_and_cannot_be_confirmed():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]), {"file": upload()}, format="multipart"
    )
    assert preview.status_code == 201
    assert [row["type"] for row in preview.data["rows"]] == ["CDSL", "NSDL"]
    assert preview.data["rows"][0]["dpid_masked"] == "—"
    assert preview.data["error_count"] == 2
    assert all(
        "PAN appears more than once in this workbook." in row["errors"]
        for row in preview.data["rows"]
    )
    assert Investor.objects.count() == 0
    assert BankAccount.objects.count() == 0

    url = reverse("account-import-preview", args=[workspace.pk, preview.data["id"]])
    confirmed = client.post(url, {"row_numbers": [2, 3]}, format="json")
    assert confirmed.status_code == 400
    assert Investor.objects.count() == 0
    assert client.post(url, {}, format="json").status_code == 400


@pytest.mark.django_db
def test_distinct_pan_rows_import_as_separate_investors():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": distinct_rows_upload()},
        format="multipart",
    )
    assert preview.status_code == 201
    assert preview.data["error_count"] == 0
    url = reverse("account-import-preview", args=[workspace.pk, preview.data["id"]])
    confirmed = client.post(url, {"row_numbers": [2, 3]}, format="json")
    assert confirmed.status_code == 200
    assert confirmed.data["created"] == {
        "investors": 2,
        "demats": 2,
        "banks": 2,
        "upis": 2,
        "payment_pending": 0,
    }
    assert Investor.objects.count() == 2
    assert all(upi.verified for upi in UPIHandle.objects.all())
    assert all(bank.current_balance == 0 for bank in BankAccount.objects.all())
    assert client.post(url, {"row_numbers": [2]}, format="json").status_code == 400


@pytest.mark.django_db
def test_existing_pan_is_an_error_in_preview_and_stale_preview_cannot_confirm():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("account-import-list", args=[workspace.pk])
    first = client.post(url, {"file": distinct_rows_upload()}, format="multipart")
    stale = client.post(url, {"file": distinct_rows_upload()}, format="multipart")
    first_url = reverse("account-import-preview", args=[workspace.pk, first.data["id"]])
    stale_url = reverse("account-import-preview", args=[workspace.pk, stale.data["id"]])
    assert client.post(first_url, {"row_numbers": [2]}, format="json").status_code == 200
    assert client.post(stale_url, {"row_numbers": [2]}, format="json").status_code == 400
    repeated = client.post(url, {"file": distinct_rows_upload()}, format="multipart")
    assert repeated.data["error_count"] == 1
    assert "PAN already belongs" in repeated.data["rows"][0]["errors"][0]
    assert Investor.objects.count() == 1


@pytest.mark.django_db
def test_account_import_rejects_unknown_selected_row_without_persisting():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": distinct_rows_upload()},
        format="multipart",
    )
    response = client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {"row_numbers": [2, 999]},
        format="json",
    )
    assert response.status_code == 400
    assert Investor.objects.count() == 0


@pytest.mark.django_db
def test_account_import_accepts_single_sheet_with_excel_generated_title():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {
            "file": edited_upload(
                "xl/workbook.xml",
                b'name="AccountImportTemplate"',
                b'name="Worksheet"',
            )
        },
        format="multipart",
    )
    assert response.status_code == 201
    assert response.data["row_count"] == 2
    assert response.data["error_count"] == 2
    assert AccountImportBatch.objects.count() == 1


@pytest.mark.django_db
def test_account_import_rejects_populated_extra_column():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {
            "file": edited_upload(
                "xl/worksheets/sheet1.xml",
                b"</row></sheetData>",
                b'<c r="I3" t="inlineStr"><is><t>Unexpected</t></is></c></row></sheetData>',
            )
        },
        format="multipart",
    )
    assert response.status_code == 400
    assert AccountImportBatch.objects.count() == 0


@pytest.mark.django_db
def test_account_import_preview_is_readable_but_viewer_cannot_confirm():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    from accounts.models import WorkspaceMembership

    WorkspaceMembership.objects.create(
        workspace=workspace, user=viewer, role=WorkspaceMembership.Role.VIEWER
    )
    client = APIClient()
    client.force_authenticate(owner)
    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]), {"file": upload()}, format="multipart"
    )
    batch = AccountImportBatch.objects.get(pk=preview.data["id"])
    client.force_authenticate(viewer)
    assert (
        client.get(reverse("account-import-preview", args=[workspace.pk, batch.pk])).status_code
        == 200
    )
    assert (
        client.post(
            reverse("account-import-preview", args=[workspace.pk, batch.pk]),
            {"row_numbers": [2]},
            format="json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_invalid_workbook_row_is_shown_and_default_confirmation_skips_it():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)

    preview = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": invalid_pan_upload()},
        format="multipart",
    )
    assert preview.status_code == 201
    assert preview.data["error_count"] == 1
    assert "PAN must use" in preview.data["rows"][0]["errors"][0]

    confirmed = client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {},
        format="json",
    )
    assert confirmed.status_code == 200
    assert confirmed.data["imported_rows"] == 1
    assert Investor.objects.count() == 1
