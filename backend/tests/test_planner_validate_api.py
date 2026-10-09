from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_preview_api import setup_workspace

from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from planner.models import PlanRun


def edited_row(investor, ipo):
    demat = DematAccount.objects.get(investor=investor)
    bank = BankAccount.objects.get(owner=investor)
    upi = UPIHandle.objects.get(bank=bank)
    return {
        "ipo": str(ipo.pk),
        "applicant": str(investor.pk),
        "category": "RETAIL",
        "lots": 1,
        "demat": str(demat.pk),
        "bank": str(bank.pk),
        "upi": str(upi.pk),
        "locked": False,
    }


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_category_and_lots_recalculate_exact_amount_and_revalidate_cash():
    owner, workspace, investor, ipo, _ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-validate", args=[workspace.pk])
    original = edited_row(investor, ipo)
    retail = client.post(url, {"rows": [original]}, format="json")
    assert retail.status_code == 200
    assert retail.data["status"] == "READY"
    assert retail.data["rows"][0]["amount"] == "15000.00"
    shni = client.post(url, {"rows": [original | {"category": "SHNI", "lots": 14}]}, format="json")
    assert shni.status_code == 200
    assert shni.data["rows"][0]["amount"] == "210000.00"
    assert shni.data["status"] == "BLOCKED"
    assert "CASH_OVERSPEND" in shni.data["rows"][0]["blocking_reasons"]
    assert PlanRun.objects.count() == 0


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_invalid_retail_lots_and_duplicate_applicant_ipo_are_blocking():
    owner, workspace, investor, ipo, _ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-validate", args=[workspace.pk])
    original = edited_row(investor, ipo)
    invalid_lots = client.post(url, {"rows": [original | {"lots": 2}]}, format="json")
    assert invalid_lots.status_code == 200
    assert invalid_lots.data["rows"][0]["amount"] == "30000.00"
    assert "INVALID_CATEGORY" in invalid_lots.data["rows"][0]["blocking_reasons"]
    duplicate = client.post(url, {"rows": [original, original]}, format="json")
    assert duplicate.status_code == 200
    assert "DUPLICATE_APPLICANT_IPO" in duplicate.data["rows"][0]["blocking_reasons"]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_changed_applicant_rechecks_demat_duplicate_and_active_state():
    owner, workspace, investor, ipo, _ = setup_workspace()
    other = Investor(workspace=workspace, name="Other Synthetic", active=True)
    other.set_pan("TESTX0002B")
    other.save()
    other_demat = DematAccount(investor=other, depository="NSDL")
    other_demat.set_dp_id("DEMO-DP-002")
    other_demat.set_client_id("DEMO-CLIENT-002")
    other_demat.save()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-validate", args=[workspace.pk])
    original = edited_row(investor, ipo)
    changed = original | {"applicant": str(other.pk), "demat": str(other_demat.pk)}

    valid = client.post(url, {"rows": [changed]}, format="json")
    assert valid.status_code == 200
    assert "INVALID_DEMAT" not in valid.data["rows"][0]["blocking_reasons"]
    assert "APPLICANT_INACTIVE" not in valid.data["rows"][0]["blocking_reasons"]

    duplicate = client.post(
        url, {"rows": [original, changed | {"applicant": str(investor.pk)}]}, format="json"
    )
    assert duplicate.status_code == 200
    assert "DUPLICATE_APPLICANT_IPO" in duplicate.data["rows"][1]["blocking_reasons"]
    assert "INVALID_DEMAT" in duplicate.data["rows"][1]["blocking_reasons"]

    other.active = False
    other.save(update_fields=["active", "updated_at"])
    inactive = client.post(url, {"rows": [changed]}, format="json")
    assert "APPLICANT_INACTIVE" in inactive.data["rows"][0]["blocking_reasons"]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_selected_ipo_scope_and_member_scope_apply_to_validation():
    owner, workspace, investor, ipo, decision = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-validate", args=[workspace.pk])
    row = edited_row(investor, ipo)
    decision.decision = "SKIP"
    decision.save(update_fields=["decision", "updated_at"])
    assert client.post(url, {"rows": [row]}, format="json").status_code == 400


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_inactive_or_other_applicants_demat_blocks_the_edited_row():
    owner, workspace, investor, ipo, _ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-validate", args=[workspace.pk])
    row = edited_row(investor, ipo)
    own_demat = DematAccount.objects.get(investor=investor)
    own_demat.active = False
    own_demat.save(update_fields=["active", "updated_at"])
    inactive = client.post(url, {"rows": [row]}, format="json")
    assert inactive.status_code == 200
    assert "INVALID_DEMAT" in inactive.data["rows"][0]["blocking_reasons"]

    other = Investor(workspace=workspace, name="Other Synthetic")
    other.set_pan("TESTX0002B")
    other.save()
    other_demat = DematAccount(investor=other, depository="NSDL")
    other_demat.set_dp_id("DEMO-DP-002")
    other_demat.set_client_id("DEMO-CLIENT-002")
    other_demat.save()
    cross = client.post(url, {"rows": [row | {"demat": str(other_demat.pk)}]}, format="json")
    assert cross.status_code == 200
    assert "INVALID_DEMAT" in cross.data["rows"][0]["blocking_reasons"]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_bank_cash_and_upi_amount_limit_revalidate_after_mapping_change():
    owner, workspace, investor, ipo, _ = setup_workspace()
    original = edited_row(investor, ipo)
    low_bank = BankAccount(
        workspace=workspace,
        owner=investor,
        bank_name="Low Balance Bank",
        current_balance=Decimal("1000.00"),
    )
    low_bank.set_account_number("DEMO-ACCOUNT-0002")
    low_bank.save()
    limited_upi = UPIHandle(
        bank=low_bank,
        holder=investor,
        verified=True,
        amount_limit_override=Decimal("10000.00"),
    )
    limited_upi.set_handle("limited@upi.test")
    limited_upi.save()
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        reverse("planner-validate", args=[workspace.pk]),
        {"rows": [original | {"bank": str(low_bank.pk), "upi": str(limited_upi.pk)}]},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "BLOCKED"
    assert "CASH_OVERSPEND" in response.data["rows"][0]["blocking_reasons"]
    assert "UPI_LIMIT_EXCEEDED" in response.data["rows"][0]["blocking_reasons"]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_lm004_lm006_lm007_custom_manual_mapping_and_lots_stay_exact():
    owner, workspace, investor, ipo, decision = setup_workspace()
    decision.mode = "CUSTOM"
    decision.save(update_fields=["mode", "updated_at"])
    original = edited_row(investor, ipo)
    alternate = BankAccount(
        workspace=workspace,
        owner=investor,
        bank_name="Alternate Synthetic Bank",
        current_balance=Decimal("230000.00"),
    )
    alternate.set_account_number("DEMO-ACCOUNT-0002")
    alternate.save()
    upi = UPIHandle(
        bank=alternate,
        holder=investor,
        verified=True,
        amount_limit_override=Decimal("220000.00"),
    )
    upi.set_handle("alternate@upi.test")
    upi.save()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-validate", args=[workspace.pk])
    row = original | {"bank": str(alternate.pk), "upi": str(upi.pk)}
    retail = client.post(url, {"rows": [row]}, format="json")
    assert retail.data["status"] == "READY"
    assert retail.data["rows"][0]["bank"] == str(alternate.pk)
    shni = client.post(url, {"rows": [row | {"category": "SHNI", "lots": 14}]}, format="json")
    assert shni.data["status"] == "READY"
    assert len(shni.data["rows"]) == 1
    assert shni.data["rows"][0]["amount"] == "210000.00"
    increased = client.post(url, {"rows": [row | {"category": "SHNI", "lots": 15}]}, format="json")
    assert increased.data["rows"][0]["amount"] == "225000.00"
    assert increased.data["status"] == "BLOCKED"
    assert "UPI_LIMIT_EXCEEDED" in increased.data["rows"][0]["blocking_reasons"]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_qc008_custom_mode_preserves_fixed_retail_and_shni_categories_on_replan():
    owner, workspace, first, ipo, decision = setup_workspace()
    decision.mode = "CUSTOM"
    decision.save(update_fields=["mode", "updated_at"])
    retail = edited_row(first, ipo)
    second = Investor(workspace=workspace, name="Second Synthetic")
    second.set_pan("TESTX0002B")
    second.save()
    demat = DematAccount(investor=second, depository="CDSL")
    demat.set_dp_id("DEMO-DP-002")
    demat.set_client_id("DEMO-CLIENT-002")
    demat.save()
    bank = BankAccount(
        workspace=workspace,
        owner=second,
        bank_name="Second Bank",
        current_balance=Decimal("230000.00"),
    )
    bank.set_account_number("DEMO-ACCOUNT-0002")
    bank.save()
    upi = UPIHandle(bank=bank, holder=second, verified=True)
    upi.set_handle("second@upi.test")
    upi.save()
    shni = {
        "ipo": str(ipo.pk),
        "applicant": str(second.pk),
        "category": "SHNI",
        "lots": 14,
        "demat": str(demat.pk),
        "bank": str(bank.pk),
        "upi": str(upi.pk),
        "locked": True,
    }
    client = APIClient()
    client.force_authenticate(owner)
    validated = client.post(
        reverse("planner-validate", args=[workspace.pk]),
        {"rows": [retail, shni]},
        format="json",
    )
    assert validated.status_code == 200
    assert validated.data["status"] == "READY"
    fixed = validated.data["rows"]
    assert {(row["applicant"], row["category"], row["amount"]) for row in fixed} == {
        (str(first.pk), "RETAIL", "15000.00"),
        (str(second.pk), "SHNI", "210000.00"),
    }
    preview = client.post(
        reverse("planner-preview", args=[workspace.pk]),
        {"locked_rows": fixed},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.data["status"] == "READY"
    assert {(row["applicant"], row["category"], row["amount"]) for row in preview.data["rows"]} == {
        (str(first.pk), "RETAIL", "15000.00"),
        (str(second.pk), "SHNI", "210000.00"),
    }


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_cross_funding_policy_and_owner_cash_warning_are_visible():
    owner, workspace, investor, ipo, _ = setup_workspace()
    original = edited_row(investor, ipo)
    other = Investor(workspace=workspace, name="Other Synthetic")
    other.set_pan("TESTX0002B")
    other.save()
    cross_bank = BankAccount(
        workspace=workspace,
        owner=other,
        bank_name="Cross Bank",
        current_balance=Decimal("50000.00"),
        cross_funding_policy="DISALLOW",
    )
    cross_bank.set_account_number("DEMO-ACCOUNT-0002")
    cross_bank.save()
    cross_upi = UPIHandle(bank=cross_bank, holder=other, verified=True)
    cross_upi.set_handle("cross@upi.test")
    cross_upi.save()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("planner-validate", args=[workspace.pk])
    denied = client.post(
        url,
        {"rows": [original | {"bank": str(cross_bank.pk), "upi": str(cross_upi.pk)}]},
        format="json",
    )
    assert "CROSS_FUNDING_DISALLOWED" in denied.data["rows"][0]["blocking_reasons"]
    assert "CROSS_FUNDING" in denied.data["rows"][0]["warnings"]

    owner_bank = BankAccount.objects.get(owner=investor)
    owner_bank.current_balance = Decimal("15000.00")
    owner_bank.save(update_fields=["current_balance", "updated_at"])
    other_demat = DematAccount(investor=other, depository="NSDL")
    other_demat.set_dp_id("DEMO-DP-002")
    other_demat.set_client_id("DEMO-CLIENT-002")
    other_demat.save()
    warning = client.post(
        url,
        {"rows": [original | {"applicant": str(other.pk), "demat": str(other_demat.pk)}]},
        format="json",
    )
    assert warning.status_code == 200
    assert warning.data["status"] == "READY"
    assert "OWNER_RESERVE_TRADEOFF" in warning.data["rows"][0]["warnings"]
