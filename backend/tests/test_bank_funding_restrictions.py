import pytest
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import make_investor, setup_plan

from accounts.models import User
from applications.services import start_tracking_plan
from core.models import AuditEvent
from exports.services import export_saved_plan
from funding.models import BankAccount, BankFundingRestriction, UPIHandle
from funding.policy import resolve_cross_funding_policy
from funding.restrictions import bank_name_restricted
from planner.persistence import create_plan_run
from planner.policies import bank_policy
from planner.snapshot_builder import build_snapshot


@pytest.mark.django_db
def test_idfc_and_boi_are_seeded_and_match_exact_normalized_names():
    assert BankFundingRestriction.objects.filter(name="IDFC", active=True).exists()
    assert BankFundingRestriction.objects.filter(name="BOI", active=True).exists()
    assert bank_name_restricted("IDFC First Bank")
    assert bank_name_restricted("Bank of India")
    assert bank_name_restricted("BOI")
    assert not bank_name_restricted("Bank of India Cooperative")
    assert not bank_name_restricted("HDFC Bank")


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_restriction_blocks_cross_funding_but_allows_own_bank_and_changes_live():
    owner, workspace, _ = setup_plan()
    bank = BankAccount.objects.get(workspace=workspace)
    bank.bank_name = "IDFC First Bank"
    bank.cross_funding_policy = "ALLOW"
    bank.save(update_fields=["bank_name", "cross_funding_policy", "updated_at"])
    assert bank_policy(bank) == "DISALLOW"
    assert build_snapshot(workspace=workspace).banks[0].cross_funding_policy == "DISALLOW"
    client = APIClient()
    client.force_authenticate(owner)
    response = client.get(reverse("bank-list", args=[workspace.pk]))
    assert response.data[0]["effective_cross_funding_policy"] == "DISALLOW"
    own = resolve_cross_funding_policy(
        platform_default="ALLOW", bank_policy=bank_policy(bank), same_owner=True
    )
    cross = resolve_cross_funding_policy(
        platform_default="ALLOW", bank_policy=bank_policy(bank), plan_override="ALLOW"
    )
    assert own.allowed_for_automation
    assert not cross.allowed_for_automation
    assert cross.blocking_reasons == ("CROSS_FUNDING_DISALLOWED",)
    restriction = BankFundingRestriction.objects.get(name="IDFC")
    restriction.active = False
    restriction.save(update_fields=["active", "updated_at"])
    assert bank_policy(bank) == "ALLOW"
    restriction.active = True
    restriction.save(update_fields=["active", "updated_at"])
    assert bank_policy(bank) == "DISALLOW"


@pytest.mark.django_db
def test_founder_can_edit_bank_list_after_mfa_and_change_is_audited():
    founder = User.objects.create_superuser(email="founder@example.test", password="test")
    staff = Client()
    staff.force_login(founder)
    list_url = reverse("founder_admin:funding_bankfundingrestriction_changelist")
    assert staff.get(list_url).status_code == 302
    session = staff.session
    session["admin_mfa_verified"] = True
    session.save()
    assert staff.get(list_url).status_code == 200
    response = staff.post(
        reverse("founder_admin:funding_bankfundingrestriction_add"),
        {
            "name": "Example Bank",
            "aliases": "Example Payments Bank",
            "reason": "Founder preference",
            "active": "on",
            "_save": "Save",
        },
    )
    assert response.status_code == 302
    assert bank_name_restricted("example-payments bank")
    assert AuditEvent.objects.filter(action="funding.bank_restriction.created").exists()


@pytest.mark.django_db
def test_existing_saved_cross_funded_plan_must_be_replanned_before_export():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    bank = BankAccount.objects.get(workspace=workspace)
    bank.bank_name = "Bank of India"
    bank.owner = make_investor(workspace, name="Another owner", pan="TESTX0002B")
    bank.save(update_fields=["bank_name", "owner", "updated_at"])
    with pytest.raises(ValidationError, match="no longer allows cross-funding"):
        export_saved_plan(plan_run=run, actor=owner)


@pytest.mark.django_db
def test_restriction_blocks_later_application_edit_and_submission():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    application = start_tracking_plan(plan_run=run, actor=owner)[0]
    other = make_investor(workspace, name="Other owner", pan="TESTX0002B")
    bank = BankAccount(workspace=workspace, owner=other, bank_name="IDFC", current_balance=50000)
    bank.set_account_number("DEMO-ACCOUNT-0002")
    bank.save()
    upi = UPIHandle(bank=bank, holder=other, verified=True)
    upi.set_handle("other@upi.test")
    upi.save()
    client = APIClient()
    client.force_authenticate(owner)
    edit_url = reverse("application-action", args=[workspace.pk, application.pk, "edit"])
    response = client.post(
        edit_url,
        {"category": "RETAIL", "lots": 1, "bank": str(bank.pk), "upi": str(upi.pk)},
        format="json",
    )
    assert response.status_code == 409
    assert "cannot fund another investor" in response.data["detail"]
    original_bank = application.bank
    original_bank.owner = other
    original_bank.bank_name = "BOI"
    original_bank.save(update_fields=["owner", "bank_name", "updated_at"])
    submit_url = reverse("application-action", args=[workspace.pk, application.pk, "submit"])
    response = client.post(submit_url, {}, format="json")
    assert response.status_code == 409
    assert "cannot fund another investor" in response.data["detail"]
