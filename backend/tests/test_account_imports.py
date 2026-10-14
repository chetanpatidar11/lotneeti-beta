import io
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

from accounts.models import User
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import BankAccount, UPIHandle
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


def seventeen_rows_six_upis_upload():
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
                for index in range(17):
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
def test_sample_account_workbook_previews_masked_rows_and_confirms_only_selected_rows():
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
    assert preview.data["rows"][0]["account_masked"] == "••••6789"
    assert "ABCDE1234F" not in str(preview.data)

    batch = AccountImportBatch.objects.get(pk=preview.data["id"])
    assert "ABCDE1234F" not in batch.rows_ciphertext
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
    assert preview.data["rows"][0]["payment_pending"] is True
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
def test_one_file_import_keeps_shared_upi_as_hint_without_fabricated_banks():
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
    assert preview.data["error_count"] == 0
    assert all(row["payment_pending"] for row in preview.data["rows"])
    assert all(row["payment_reference"] == "••••name" for row in preview.data["rows"])
    assert "somename@upi" not in str(preview.data)

    result = client.post(
        reverse("account-import-preview", args=[workspace.pk, preview.data["id"]]),
        {"row_numbers": [2, 3]},
        format="json",
    )
    assert result.status_code == 200
    assert result.data["created"] == {
        "investors": 2,
        "demats": 2,
        "banks": 0,
        "upis": 0,
        "payment_pending": 2,
    }
    assert BankAccount.objects.count() == 0
    assert UPIHandle.objects.count() == 0
    assert all(investor.payment_setup_pending for investor in Investor.objects.all())
    assert all(
        investor.payment_hint_masked == "••••name@upi" for investor in Investor.objects.all()
    )
    assert all(not applicant.active for applicant in build_snapshot(workspace=workspace).applicants)

    funded = Investor.objects.order_by("id").first()
    bank = BankAccount(workspace=workspace, owner=funded, bank_name="Synthetic Bank")
    bank.set_account_number("123400001111")
    bank.save()
    upi = UPIHandle(bank=bank, holder=funded, verified=True)
    upi.set_handle("owner@upi")
    upi.save()
    applicant_state = {
        applicant.id: applicant.active
        for applicant in build_snapshot(workspace=workspace).applicants
    }
    assert applicant_state[str(funded.pk)] is True
    assert sum(applicant_state.values()) == 1


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
        {"row_numbers": list(range(2, 19))},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["created"] == {
        "investors": 17,
        "demats": 17,
        "banks": 0,
        "upis": 0,
        "payment_pending": 17,
    }


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
    assert all(not upi.verified for upi in UPIHandle.objects.all())
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
