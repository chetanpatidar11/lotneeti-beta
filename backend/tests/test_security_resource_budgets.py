import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_account_imports import edited_upload, seventeen_rows_six_upis_upload
from test_planner_preview_api import setup_workspace
from test_planner_validate_api import edited_row
from test_recurring_scheduler import make_schedule

from core.crypto import encrypt_value
from funding.models import RecurringDebit, RecurringDebitOccurrence
from funding.recurring import post_due_recurring_debits
from investors.models import AccountImportBatch
from planner.views import MAX_EDITED_ROWS, MAX_LOCKED_ROWS, PreviewRequestSerializer


@pytest.mark.django_db
def test_legacy_oversized_preview_cannot_be_read_or_confirmed():
    owner, workspace, *_ = setup_workspace()
    batch = AccountImportBatch.objects.create(
        workspace=workspace,
        created_by=owner,
        source_filename="Legacy.xlsx",
        source_hash="legacy",
        row_count=101,
        error_count=0,
        rows_ciphertext=encrypt_value(
            json.dumps([{"row_number": n, "errors": []} for n in range(1, 102)]),
            purpose="account-import",
        ),
    )
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("account-import-preview", args=[workspace.pk, batch.pk])
    assert client.get(url).status_code == 400
    with patch("investors.account_imports.Investor.objects.filter") as lookup:
        response = client.post(url, {}, format="json")
    assert response.status_code == 400
    lookup.assert_not_called()
    batch.refresh_from_db()
    assert batch.status == AccountImportBatch.Status.PREVIEWED


@pytest.mark.django_db
@pytest.mark.parametrize("sparse", [False, True])
def test_blank_and_sparse_workbook_rows_cannot_bypass_work_budget(sparse):
    owner, workspace, *_ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    rows = b"".join(
        f'<row r="{index + 10 if sparse else 4}"></row>'.encode() for index in range(101)
    )
    workbook = edited_upload("xl/worksheets/sheet1.xml", b"</sheetData>", rows + b"</sheetData>")
    response = client.post(
        reverse("account-import-list", args=[workspace.pk]), {"file": workbook}, format="multipart"
    )
    assert response.status_code == 400
    assert AccountImportBatch.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("count,expected", [(100, 201), (101, 400)])
def test_workbook_row_budget_precedes_preview_persistence(count, expected):
    owner, workspace, *_ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        reverse("account-import-list", args=[workspace.pk]),
        {"file": seventeen_rows_six_upis_upload(count)},
        format="multipart",
    )
    assert response.status_code == expected
    assert AccountImportBatch.objects.count() == int(expected == 201)
    if expected == 400:
        assert "100" in response.data["detail"]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_duplicate_and_oversized_locks_never_enter_snapshot_or_engine():
    owner, workspace, investor, ipo, _ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    row = edited_row(investor, ipo) | {"amount": "15000.00"}
    url = reverse("planner-preview", args=[workspace.pk])
    for rows in ([row, row | {"category": "SHNI"}], [row] * (MAX_LOCKED_ROWS + 1)):
        with patch("planner.views.build_snapshot") as build:
            response = client.post(url, {"locked_rows": rows}, format="json")
        assert response.status_code == 400
        build.assert_not_called()
    pair = PreviewRequestSerializer(data={"locked_rows": [row, row | {"category": "SHARE"}]})
    assert pair.is_valid(), pair.errors


@pytest.mark.django_db
@pytest.mark.parametrize("route", ["planner-validate", "planner-run-create"])
def test_sibling_plan_collections_have_request_budget(route):
    owner, workspace, investor, ipo, _ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    row = edited_row(investor, ipo)
    with patch("planner.views.build_snapshot") as build:
        response = client.post(
            reverse(route, args=[workspace.pk]),
            {"rows": [row] * (MAX_EDITED_ROWS + 1)},
            format="json",
        )
    assert response.status_code == 400
    build.assert_not_called()


@pytest.mark.django_db
def test_ancient_recurring_backlog_is_bounded_fair_and_resumable():
    bank, old = make_schedule(amount="0.01")
    old.frequency = "DAILY"
    old.start_date = old.next_due_date = date(1, 1, 1)
    old.save()
    ordinary = RecurringDebit.objects.create(
        bank=bank,
        name="Ordinary",
        amount=Decimal("1.00"),
        frequency="MONTHLY",
        start_date=date(2026, 10, 5),
        next_due_date=date(2026, 10, 5),
    )
    assert post_due_recurring_debits(as_of=date(2026, 10, 5)) == 11
    old.refresh_from_db()
    ordinary.refresh_from_db()
    assert old.next_due_date == date(1, 1, 11)
    assert ordinary.next_due_date == date(2026, 11, 5)
    assert post_due_recurring_debits(as_of=date(2026, 10, 5)) == 10
    old.refresh_from_db()
    assert old.next_due_date == date(1, 1, 21)
    assert RecurringDebitOccurrence.objects.filter(recurring_debit=old).count() == 20
    bank.refresh_from_db()
    assert bank.current_balance == Decimal("49998.80")


@pytest.mark.django_db
def test_global_and_schedule_budgets_rotate_without_skipping_occurrences(monkeypatch):
    bank, first = make_schedule(amount="0.01")
    first.frequency = "DAILY"
    first.next_due_date = first.start_date = date(2026, 1, 1)
    first.save()
    second = RecurringDebit.objects.create(
        bank=bank,
        name="Second",
        amount=Decimal("0.01"),
        frequency="DAILY",
        start_date=date(2026, 1, 1),
        next_due_date=date(2026, 1, 1),
    )
    monkeypatch.setattr("funding.recurring.MAX_SCHEDULES_PER_RUN", 1)
    monkeypatch.setattr("funding.recurring.MAX_OCCURRENCES_PER_RUN", 2)
    assert post_due_recurring_debits(as_of=date(2026, 10, 5)) == 2
    assert post_due_recurring_debits(as_of=date(2026, 10, 5)) == 2
    for schedule in (first, second):
        schedule.refresh_from_db()
        assert schedule.next_due_date == date(2026, 1, 1) + timedelta(days=2)
        assert RecurringDebitOccurrence.objects.filter(recurring_debit=schedule).count() == 2
