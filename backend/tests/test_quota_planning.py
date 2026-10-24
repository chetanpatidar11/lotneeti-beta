from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_preview_api import setup_workspace

from applications.models import Application
from applications.services import start_tracking_plan
from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.quota_terms import shareholder_terms_fingerprint
from planner.engine import generate_proposal
from planner.models import PlanRun
from planner.quota_planning import generate_quota_proposal, quota_context
from planner.snapshot_builder import build_snapshot


def setup_quota(*, count=15, eligible_count=8, balance="250000"):
    owner, workspace, first, ipo, decision = setup_workspace()
    BankAccount.objects.filter(workspace=workspace).update(current_balance=Decimal(balance))
    investors = [first]
    for index in range(1, count):
        investor = Investor(
            workspace=workspace,
            name=f"Synthetic quota investor {index:02}",
            planning_priority=index + 1,
        )
        investor.set_pan(f"TESTX{index + 1:04}A")
        investor.save()
        demat = DematAccount(investor=investor, depository="CDSL")
        demat.set_dp_id(f"SYNTHETIC-DP-{index}")
        demat.set_client_id(f"SYNTHETIC-CLIENT-{index}")
        demat.save()
        bank = BankAccount(
            workspace=workspace,
            owner=investor,
            bank_name=f"Synthetic quota bank {index}",
            current_balance=Decimal(balance),
        )
        bank.set_account_number(f"SYNTHETIC-ACCOUNT-{index}")
        bank.save()
        upi = UPIHandle(bank=bank, holder=investor, verified=True)
        upi.set_handle(f"synthetic-{index}@quota.test")
        upi.save()
        investors.append(investor)
    ipo.shareholder_quota = True
    ipo.shareholder_terms_url = "https://issuer.example.test/confirmed-shareholder-terms"
    ipo.save()
    decision.shareholder_preferred = True
    decision.shareholder_terms_fingerprint = shareholder_terms_fingerprint(ipo)
    decision.save()
    decision.shareholder_eligible.set(investors[:eligible_count])
    client = APIClient()
    client.force_authenticate(owner)
    return owner, workspace, investors, ipo, decision, client


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_fifteen_public_plus_eight_maximum_shareholder_rows_preserve_normal_mappings():
    _, workspace, investors, ipo, _, client = setup_quota()
    snapshot = build_snapshot(workspace=workspace)
    context = quota_context(workspace, snapshot)
    original = generate_proposal(snapshot)
    extended = generate_quota_proposal(snapshot, context)
    public = tuple(row for row in extended.coverage.rows if row.category != "SHARE")
    assert public == original.coverage.rows
    assert len(public) == 15
    share = tuple(row for row in extended.coverage.rows if row.category == "SHARE")
    assert len(share) == 8
    assert {row.applicant_id for row in share} == {str(item.pk) for item in investors[:8]}
    assert all(row.lots == 13 and row.amount == Decimal("195000") for row in share)
    assert extended.audit.valid, extended.audit.issues
    assert generate_quota_proposal(snapshot, context) == extended
    preview = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json")
    assert preview.status_code == 200
    assert preview.data["status"] == "READY", preview.data
    assert len(preview.data["rows"]) == 23
    saved = client.post(
        reverse("planner-run-create", args=[workspace.pk]),
        {"rows": preview.data["rows"]},
        format="json",
    )
    assert saved.status_code == 201, saved.data
    assert saved.data["status"] == "READY", saved.data
    run = PlanRun.objects.get()
    assert run.planner_version == "planner-v2.0+quota-v1"
    apps = start_tracking_plan(plan_run=run, actor=run.generated_by)
    assert len(apps) == 23
    for investor in investors:
        expected = 2 if investor in investors[:8] else 1
        assert Application.objects.filter(applicant=investor, ipo=ipo).count() == expected
    assert len(start_tracking_plan(plan_run=run, actor=run.generated_by)) == 23


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_disabled_quota_has_identical_legacy_proposal_and_hashes():
    _, workspace, _, _, decision, _ = setup_quota(count=2, eligible_count=1)
    decision.shareholder_preferred = False
    decision.save()
    snapshot = build_snapshot(workspace=workspace)
    assert generate_quota_proposal(
        snapshot, quota_context(workspace, snapshot)
    ) == generate_proposal(snapshot)


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_shareholder_uses_affordable_whole_lots_without_changing_public_row():
    _, workspace, _, _, _, _ = setup_quota(count=1, eligible_count=1, balance="50000")
    snapshot = build_snapshot(workspace=workspace)
    result = generate_quota_proposal(snapshot, quota_context(workspace, snapshot))
    assert result.audit.valid
    assert [(row.category, row.lots) for row in result.coverage.rows] == [
        ("RETAIL", 1),
        ("SHARE", 2),
    ]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_bhni_uses_minimum_above_ten_lakh_own_bank_asba_and_shareholder_can_coexist():
    owner, workspace, investors, _, decision, client = setup_quota(
        count=1, eligible_count=1, balance="1250000"
    )
    decision.mode = "BHNI_PREFERRED"
    decision.save()
    response = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json")
    assert response.status_code == 200
    assert response.data["status"] == "READY", response.data
    assert len(response.data["rows"]) == 2
    bhni = next(row for row in response.data["rows"] if row["category"] == "BHNI")
    assert bhni["lots"] == 67
    assert bhni["amount"] == "1005000.00"
    assert bhni["upi"] == ""
    payload = {
        "rows": [
            row | ({"upi": None} if row["category"] == "BHNI" else {})
            for row in response.data["rows"]
        ]
    }
    checked = client.post(reverse("planner-validate", args=[workspace.pk]), payload, format="json")
    assert checked.status_code == 200 and checked.data["status"] == "READY", checked.data
    saved = client.post(reverse("planner-run-create", args=[workspace.pk]), payload, format="json")
    assert saved.status_code == 201 and saved.data["status"] == "READY", saved.data
    apps = start_tracking_plan(plan_run=PlanRun.objects.get(), actor=owner)
    assert len(apps) == 2
    for app in apps:
        submitted = client.post(
            reverse("application-action", args=[workspace.pk, app.pk, "submit"]), {}
        )
        assert submitted.status_code == 200, submitted.data
    app = Application.objects.get(category="BHNI")
    assert app.upi_id is None and app.bank.owner_id == investors[0].pk
    assert (
        client.post(
            reverse("application-action", args=[workspace.pk, app.pk, "block"]), {}
        ).status_code
        == 200
    )


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_eligibility_is_explicit_scoped_and_unavailable_without_confirmed_quota():
    from accounts.models import User, WorkspaceMembership
    from accounts.services import create_workspace

    owner, workspace, investors, ipo, decision, client = setup_quota(count=2, eligible_count=1)
    url = reverse("workspace-ipo-decision-detail", args=[workspace.pk, ipo.pk])
    other_workspace = create_workspace(name="Other synthetic quota", owner=owner)
    outsider = Investor(workspace=other_workspace, name="Other synthetic investor")
    outsider.set_pan("OTHXX0001A")
    outsider.save()
    for eligible in ([], [str(outsider.pk)], [str(investors[0].pk), str(investors[0].pk)]):
        result = client.patch(
            url, {"shareholder_preferred": True, "shareholder_eligible": eligible}, format="json"
        )
        assert result.status_code == 400
    investors[1].active = False
    investors[1].save()
    assert (
        client.patch(
            url,
            {"shareholder_preferred": True, "shareholder_eligible": [str(investors[1].pk)]},
            format="json",
        ).status_code
        == 400
    )
    ipo.shareholder_quota = False
    ipo.save()
    assert (
        client.patch(
            url,
            {"shareholder_preferred": True, "shareholder_eligible": [str(investors[0].pk)]},
            format="json",
        ).status_code
        == 400
    )
    viewer = User.objects.create_user(email="quota-viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert client.patch(url, {"shareholder_preferred": False}, format="json").status_code == 403
    decision.refresh_from_db()
    assert decision.shareholder_preferred is True
    assert list(decision.shareholder_eligible.values_list("pk", flat=True)) == [investors[0].pk]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_shareholder_duplicate_and_ineligible_rows_are_blocking_and_category_specific():
    _, workspace, investors, ipo, _, client = setup_quota(count=2, eligible_count=1)
    preview = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data
    share = next(row for row in preview["rows"] if row["category"] == "SHARE")
    duplicate = client.post(
        reverse("planner-validate", args=[workspace.pk]),
        {"rows": preview["rows"] + [share]},
        format="json",
    )
    assert duplicate.status_code == 200
    assert duplicate.data["status"] == "BLOCKED"
    assert all(
        "DUPLICATE_APPLICANT_IPO" not in row["blocking_reasons"]
        for row in duplicate.data["rows"]
        if row["category"] == "RETAIL"
    )
    invalid = share | {
        "applicant": str(investors[1].pk),
        "demat": str(DematAccount.objects.get(investor=investors[1]).pk),
    }
    rejected = client.post(
        reverse("planner-validate", args=[workspace.pk]), {"rows": [invalid]}, format="json"
    )
    assert rejected.status_code == 200
    assert "SHAREHOLDER_INELIGIBLE" in rejected.data["rows"][0]["blocking_reasons"]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_bhni_rejects_exact_boundary_foreign_owner_upi_and_provisional_account():
    _, workspace, investors, _, decision, client = setup_quota(
        count=2, eligible_count=0, balance="1500000"
    )
    decision.shareholder_preferred = False
    decision.mode = "BHNI_PREFERRED"
    decision.save()
    preview = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data
    row = preview["rows"][0] | {"upi": None}
    url = reverse("planner-validate", args=[workspace.pk])
    for changes in (
        {"lots": 66, "amount": "990000.00"},
        {"bank": str(BankAccount.objects.exclude(pk=row["bank"]).get().pk)},
    ):
        rejected = client.post(url, {"rows": [row | changes]}, format="json")
        assert rejected.status_code == 200
        assert rejected.data["status"] == "BLOCKED"
    upi = UPIHandle.objects.get(bank_id=row["bank"])
    assert (
        client.post(url, {"rows": [row | {"upi": str(upi.pk)}]}, format="json").status_code == 400
    )
    BankAccount.objects.filter(pk=row["bank"]).update(is_imported_reference=True)
    rejected = client.post(url, {"rows": [row]}, format="json")
    assert rejected.status_code == 200
    assert "ASBA_OWN_BANK_REQUIRED" in rejected.data["rows"][0]["blocking_reasons"]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_bhni_saved_planned_list_has_asba_and_no_fake_upi():
    _, workspace, _, _, decision, client = setup_quota(count=1, eligible_count=0, balance="1250000")
    decision.shareholder_preferred = False
    decision.mode = "BHNI_PREFERRED"
    decision.save()
    preview = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data
    saved = client.post(
        reverse("planner-run-create", args=[workspace.pk]),
        {"rows": [row | {"upi": None} for row in preview["rows"]]},
        format="json",
    )
    assert saved.status_code == 201
    response = client.get(reverse("application-list", args=[workspace.pk]))
    assert response.status_code == 200, response.data
    assert response.data[0]["category"] == "BHNI"
    assert response.data[0]["upi_label"] == "Bank ASBA"


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_quota_csv_keeps_categories_amounts_and_asba_separate():
    import csv
    from io import StringIO

    from exports.services import export_saved_plan

    owner, workspace, _, _, decision, client = setup_quota(
        count=1, eligible_count=1, balance="1250000"
    )
    decision.mode = "BHNI_PREFERRED"
    decision.save()
    rows = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data[
        "rows"
    ]
    saved = client.post(
        reverse("planner-run-create", args=[workspace.pk]),
        {"rows": [row | ({"upi": None} if row["category"] == "BHNI" else {}) for row in rows]},
        format="json",
    )
    assert saved.status_code == 201
    run = PlanRun.objects.get()
    with pytest.raises(ValidationError, match="quota CSV"):
        export_saved_plan(plan_run=run, actor=owner)
    artifact = export_saved_plan(plan_run=run, actor=owner, format_id="quota_csv")
    records = list(csv.DictReader(StringIO(artifact.data.decode())))
    assert len(records) == 2
    bhni = next(item for item in records if item["Category"] == "bHNI")
    share = next(item for item in records if item["Category"] == "Shareholder")
    assert bhni["Funding method"] == "Bank ASBA" and bhni["UPI ID"] == ""
    assert bhni["Amount"] == "1005000.00" and bhni["Lots"] == "67"
    assert share["Funding method"] == "UPI" and share["UPI ID"]
    assert bhni["PAN"] == share["PAN"]


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_shareholder_and_public_locks_remain_distinct_and_count_together_for_cash():
    _, workspace, _, _, _, client = setup_quota(count=1, eligible_count=1)
    preview_url = reverse("planner-preview", args=[workspace.pk])
    rows = client.post(preview_url, {}, format="json").data["rows"]
    response = client.post(preview_url, {"locked_rows": rows}, format="json")
    assert response.status_code == 200
    assert response.data["status"] == "READY", response.data
    assert len(response.data["rows"]) == 2
    assert all(row["locked"] for row in response.data["rows"])
    BankAccount.objects.filter(workspace=workspace).update(current_balance=Decimal("200000"))
    blocked = client.post(preview_url, {"locked_rows": rows}, format="json")
    assert blocked.status_code == 200 and blocked.data["status"] == "BLOCKED"
    assert len(blocked.data["rows"]) == 2


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_active_database_uniqueness_is_separate_for_public_and_shareholder():
    from planner.models import PlanRow

    owner, workspace, _, _, _, client = setup_quota(count=1, eligible_count=1)
    rows = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data[
        "rows"
    ]
    assert (
        client.post(
            reverse("planner-run-create", args=[workspace.pk]), {"rows": rows}, format="json"
        ).status_code
        == 201
    )
    run = PlanRun.objects.get()
    applications = start_tracking_plan(plan_run=run, actor=owner)
    assert len(applications) == 2
    for index, item in enumerate(applications):
        original_row = item.plan_row
        duplicate_row = PlanRow.objects.get(pk=original_row.pk)
        duplicate_row.pk = None
        duplicate_row.position = 100 + index
        duplicate_row.save()
        item.pk = None
        item.plan_row = duplicate_row
        with pytest.raises(ValidationError):
            item.save()
    assert Application.objects.count() == 2


@pytest.mark.django_db
def test_shareholder_terms_require_evidence_and_do_not_modify_issue_prices():
    from core.models import AuditEvent
    from ipos.quota_terms import set_shareholder_terms

    owner, _, _, ipo, _ = setup_workspace()
    original_price = ipo.upper_price
    payload = {
        "shareholder_quota": "on",
        "shareholder_min_lots": 1,
        "shareholder_max_amount": "200000.00",
        "shareholder_record_date": "2026-10-14",
        "reason": "Synthetic verified offer terms",
    }
    with pytest.raises(ValidationError):
        set_shareholder_terms(ipo=ipo, actor=owner, data=payload)
    updated = set_shareholder_terms(
        ipo=ipo,
        actor=owner,
        data=payload | {"shareholder_terms_url": "https://issuer.example.test/terms"},
    )
    assert updated.shareholder_quota and updated.upper_price == original_price
    assert AuditEvent.objects.filter(action="ipo.shareholder_terms_updated").count() == 1


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_changed_shareholder_terms_require_new_confirmation_before_plan_or_tracking():
    from datetime import date

    owner, workspace, investors, ipo, _, client = setup_quota(count=1, eligible_count=1)
    url = reverse("planner-preview", args=[workspace.pk])
    rows = client.post(url, {}, format="json").data["rows"]
    assert (
        client.post(
            reverse("planner-run-create", args=[workspace.pk]), {"rows": rows}, format="json"
        ).status_code
        == 201
    )
    run = PlanRun.objects.get()
    ipo.shareholder_record_date = date(2026, 10, 15)
    ipo.save()
    blocked = client.post(url, {}, format="json")
    assert blocked.status_code == 200 and blocked.data["status"] == "BLOCKED"
    assert any(item["code"] == "SHAREHOLDER_TERMS_CHANGED" for item in blocked.data["audit_issues"])
    with pytest.raises(ValidationError, match="eligible"):
        start_tracking_plan(plan_run=run, actor=owner)
    assert Application.objects.count() == 0
    decision_url = reverse("workspace-ipo-decision-detail", args=[workspace.pk, ipo.pk])
    confirmed = client.patch(
        decision_url,
        {"shareholder_preferred": True, "shareholder_eligible": [str(investors[0].pk)]},
        format="json",
    )
    assert confirmed.status_code == 200 and not confirmed.data["shareholder_terms_changed"]
    assert client.post(url, {}, format="json").data["status"] == "READY"
