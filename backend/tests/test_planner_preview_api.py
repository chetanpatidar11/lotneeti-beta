from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.models import IPO, IPOUserDecision
from planner.models import PlanRun


def setup_workspace():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Synthetic family", owner=owner)
    investor = Investor(workspace=workspace, name="Synthetic Investor")
    investor.set_pan("TESTX0001A")
    investor.save()
    demat = DematAccount(investor=investor, depository="CDSL")
    demat.set_dp_id("DEMO-DP-001")
    demat.set_client_id("DEMO-CLIENT-001")
    demat.save()
    bank = BankAccount(
        workspace=workspace,
        owner=investor,
        bank_name="Synthetic Bank",
        current_balance=Decimal("50000.00"),
    )
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    upi = UPIHandle(bank=bank, holder=investor, verified=True)
    upi.set_handle("demo@upi.test")
    upi.save()
    ipo = IPO.objects.create(
        issuer_name="Synthetic Industries",
        issue_type="MAINBOARD",
        lower_price=Decimal("100.00"),
        upper_price=Decimal("100.00"),
        lot_size=150,
        open_date=date(2030, 10, 1),
        close_date=date(2030, 10, 3),
        allotment_date=date(2030, 10, 9),
        status="UPCOMING",
        publication_state="PUBLISHED",
        source_key="manual",
        source_record_id="synthetic-preview-ipo",
    )
    decision = IPOUserDecision.objects.create(workspace=workspace, ipo=ipo, decision="APPLY")
    return owner, workspace, investor, ipo, decision


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_preview_builds_scoped_snapshot_and_does_not_save_plan_or_event():
    owner, workspace, investor, ipo, _ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json")
    assert response.status_code == 200
    assert response.data["status"] == "READY"
    assert response.data["planned_total"] == "15000.00"
    assert len(response.data["rows"]) == 1
    assert response.data["rows"][0]["applicant"] == str(investor.pk)
    assert response.data["rows"][0]["ipo"] == str(ipo.pk)
    assert response.data["rows"][0]["reasons"][0]["code"] == "APPLICANT_PRIORITY"
    assert len(response.data["input_snapshot_hash"]) == 64
    assert PlanRun.objects.count() == 0
    assert AuditEvent.objects.filter(action="planner.run.generated").count() == 0


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_preview_respects_manual_skip_and_rejects_explicit_unselected_ipo():
    owner, workspace, _, ipo, decision = setup_workspace()
    decision.decision = "SKIP"
    decision.save(update_fields=["decision", "updated_at"])
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-preview", args=[workspace.pk])
    empty = client.post(url, {}, format="json")
    assert empty.status_code == 200
    assert empty.data["rows"] == []
    rejected = client.post(url, {"ipo_ids": [str(ipo.pk)]}, format="json")
    assert rejected.status_code == 400


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_preview_is_readable_by_viewer_but_hidden_from_outsider():
    owner, workspace, _, _, _ = setup_workspace()
    viewer = User.objects.create_user(email="viewer@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client = APIClient()
    url = reverse("planner-preview", args=[workspace.pk])
    client.force_authenticate(viewer)
    assert client.post(url, {}, format="json").status_code == 200
    client.force_authenticate(outsider)
    assert client.post(url, {}, format="json").status_code == 404
    client.force_authenticate(owner)
    assert client.post(url, {"ipo_ids": ["not-a-uuid"]}, format="json").status_code == 400


@pytest.mark.django_db
def test_missing_platform_policy_returns_clear_unavailable_response():
    owner, workspace, _, _, _ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    with override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY=None):
        response = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json")
    assert response.status_code == 503
    assert response.data["detail"] == "Planner policy has not been configured."


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_preview_applies_plan_cross_funding_override_without_saving_it():
    owner, workspace, _, _, _ = setup_workspace()
    beneficiary = Investor(workspace=workspace, name="Synthetic Beneficiary", planning_priority=2)
    beneficiary.set_pan("TESTX0002B")
    beneficiary.save()
    demat = DematAccount(investor=beneficiary, depository="NSDL")
    demat.set_dp_id("DEMO-DP-002")
    demat.set_client_id("DEMO-CLIENT-002")
    demat.save()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-preview", args=[workspace.pk])
    allowed = client.post(url, {}, format="json")
    denied = client.post(url, {"plan_cross_funding_override": "DISALLOW"}, format="json")
    assert allowed.status_code == denied.status_code == 200
    assert len(allowed.data["rows"]) == 2
    assert len(denied.data["rows"]) == 1
    assert denied.data["uncovered"][0]["applicant_id"] == str(beneficiary.pk)
    assert PlanRun.objects.count() == 0


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_locked_mapping_survives_replan_and_stays_visible_when_cash_falls():
    owner, workspace, investor, ipo, _ = setup_workspace()
    bank = BankAccount.objects.get(owner=investor)
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-preview", args=[workspace.pk])
    initial = client.post(url, {}, format="json")
    assert initial.status_code == 200
    original = initial.data["rows"][0]
    bank.current_balance = Decimal("1000.00")
    bank.save(update_fields=["current_balance", "updated_at"])
    replanned = client.post(url, {"locked_rows": [original]}, format="json")
    assert replanned.status_code == 200
    assert replanned.data["status"] == "BLOCKED"
    row = replanned.data["rows"][0]
    for field in ("ipo", "applicant", "category", "lots", "amount", "demat", "bank", "upi"):
        assert row[field] == original[field]
    assert row["locked"] is True
    assert "LOCKED_ROW_INFEASIBLE" in row["blocking_reasons"]
    assert PlanRun.objects.count() == 0


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_replan_rejects_locked_mapping_from_another_workspace():
    owner, workspace, _, _, _ = setup_workspace()
    other = User.objects.create_user(email="other@example.test")
    other_workspace = create_workspace(name="Other family", owner=other)
    foreign_bank = BankAccount.objects.create(
        workspace=other_workspace,
        owner=Investor.objects.create(workspace=other_workspace, name="Other investor"),
        bank_name="Other bank",
        current_balance=Decimal("50000.00"),
    )
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-preview", args=[workspace.pk])
    original = client.post(url, {}, format="json").data["rows"][0]
    response = client.post(
        url, {"locked_rows": [original | {"bank": str(foreign_bank.pk)}]}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_replan_moves_only_unlocked_row_after_its_bank_becomes_unavailable():
    owner, workspace, investor, _, _ = setup_workspace()
    own_bank = BankAccount.objects.get(owner=investor)
    own_bank.current_balance = Decimal("30000.00")
    own_bank.save(update_fields=["current_balance", "updated_at"])
    second = Investor(workspace=workspace, name="Second Synthetic", planning_priority=2)
    second.set_pan("TESTX0002B")
    second.save()
    demat = DematAccount(investor=second, depository="NSDL")
    demat.set_dp_id("DEMO-DP-002")
    demat.set_client_id("DEMO-CLIENT-002")
    demat.save()
    second_bank = BankAccount(
        workspace=workspace,
        owner=second,
        bank_name="Second Bank",
        current_balance=Decimal("15000.00"),
    )
    second_bank.set_account_number("DEMO-ACCOUNT-0002")
    second_bank.save()
    second_upi = UPIHandle(bank=second_bank, holder=second, verified=True)
    second_upi.set_handle("second@upi.test")
    second_upi.save()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-preview", args=[workspace.pk])
    initial = client.post(url, {}, format="json")
    assert initial.status_code == 200
    assert len(initial.data["rows"]) == 2
    owner_row = next(row for row in initial.data["rows"] if row["applicant"] == str(investor.pk))
    second_row = next(row for row in initial.data["rows"] if row["applicant"] == str(second.pk))
    assert second_row["bank"] == str(second_bank.pk)

    second_bank.active = False
    second_bank.save(update_fields=["active", "updated_at"])
    replanned = client.post(url, {"locked_rows": [owner_row]}, format="json")
    assert replanned.status_code == 200
    assert replanned.data["status"] == "READY"
    rows = {row["applicant"]: row for row in replanned.data["rows"]}
    assert rows[str(investor.pk)]["locked"] is True
    assert rows[str(investor.pk)]["bank"] == owner_row["bank"]
    assert rows[str(investor.pk)]["upi"] == owner_row["upi"]
    assert rows[str(second.pk)]["locked"] is False
    assert rows[str(second.pk)]["bank"] == str(own_bank.pk)
    assert rows[str(second.pk)]["bank"] != second_row["bank"]
