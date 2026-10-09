from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from ipos.models import IPO, GMPObservation, IPOUserDecision
from ipos.selection import select_ipo


def make_ipo():
    return IPO.objects.create(
        issuer_name="Synthetic Industries",
        issue_type="MAINBOARD",
        lower_price=Decimal("100.00"),
        upper_price=Decimal("100.00"),
        lot_size=150,
        open_date=date(2026, 10, 1),
        close_date=date(2026, 10, 3),
        allotment_date=date(2026, 10, 8),
        publication_state=IPO.PublicationState.PUBLISHED,
        source_key="synthetic-fixture",
        source_record_id="synthetic-001",
    )


def test_manual_choices_outrank_threshold_and_unset_values_are_not_selected():
    assert select_ipo(decision="APPLY", gmp_percent=Decimal("1"), threshold=Decimal("20")) == (
        True,
        "MANUAL_APPLY",
    )
    assert select_ipo(decision="SKIP", gmp_percent=Decimal("50"), threshold=Decimal("20")) == (
        False,
        "MANUAL_SKIP",
    )
    assert select_ipo(decision="DEFAULT", gmp_percent=Decimal("20"), threshold=Decimal("20")) == (
        True,
        "GMP_THRESHOLD",
    )
    assert select_ipo(decision="DEFAULT", gmp_percent=None, threshold=Decimal("20")) == (
        False,
        "NO_AUTO_SELECTION",
    )


@pytest.mark.parametrize(
    ("case", "decision", "gmp", "expected"),
    [
        ("IS-001", "DEFAULT", "25", True),
        ("IS-002", "DEFAULT", "12", False),
        ("IS-003", "APPLY", "8", True),
        ("IS-004", "SKIP", "35", False),
        ("IS-005", "SKIP", "40", False),
        ("IS-006", "DEFAULT", "30", True),
    ],
)
def test_matrix_selection_cases(case, decision, gmp, expected):
    selected, _ = select_ipo(decision=decision, gmp_percent=Decimal(gmp), threshold=Decimal("20"))
    assert selected is expected, case


@pytest.mark.django_db
def test_ipo_manual_apply_skip_persists_and_overrides_workspace_threshold():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    workspace.auto_select_gmp_percent = Decimal("20.00")
    workspace.save()
    ipo = make_ipo()
    GMPObservation.objects.create(
        ipo=ipo,
        source_key="synthetic",
        value_per_share=Decimal("10.00"),
        observed_at=timezone.now() - timedelta(hours=1),
    )
    client = APIClient()
    client.force_authenticate(owner)
    list_url = reverse("workspace-ipo-decision-list", args=[workspace.pk])
    detail_url = reverse("workspace-ipo-decision-detail", args=[workspace.pk, ipo.pk])
    assert client.get(list_url).data[0]["selected"] is False

    applied = client.patch(detail_url, {"decision": "APPLY"})
    assert applied.status_code == 200
    assert applied.data["selected"] is True
    assert client.get(list_url).data[0]["reason"] == "MANUAL_APPLY"
    assert IPOUserDecision.objects.get(workspace=workspace, ipo=ipo).decision == "APPLY"
    skipped = client.patch(detail_url, {"decision": "SKIP"})
    assert skipped.status_code == 200
    assert skipped.data["selected"] is False
    assert client.get(list_url).data[0]["reason"] == "MANUAL_SKIP"
    reset = client.patch(detail_url, {"decision": "DEFAULT"})
    assert reset.status_code == 200
    assert reset.data["selected"] is False
    assert reset.data["reason"] == "GMP_THRESHOLD"
    assert client.get(list_url).data[0]["decision"] == "DEFAULT"
    workspace.auto_select_gmp_percent = Decimal("5.00")
    workspace.save()
    assert client.get(list_url).data[0]["selected"] is True
    mode = client.patch(detail_url, {"mode": "SHNI_PREFERRED"})
    assert mode.status_code == 200
    assert mode.data["decision"] == "DEFAULT"
    assert mode.data["mode"] == "SHNI_PREFERRED"
    assert client.get(list_url).data[0]["mode"] == "SHNI_PREFERRED"
    assert client.patch(detail_url, {"mode": "UNSUPPORTED"}).status_code == 400
    assert client.patch(detail_url, {}).status_code == 400


@pytest.mark.django_db
def test_ipo_decision_workspace_scope_and_viewer_write_denial():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    ipo = make_ipo()
    list_url = reverse("workspace-ipo-decision-list", args=[workspace.pk])
    detail_url = reverse("workspace-ipo-decision-detail", args=[workspace.pk, ipo.pk])
    client = APIClient()
    client.force_authenticate(outsider)
    assert client.get(list_url).status_code == 403
    client.force_authenticate(viewer)
    assert client.get(list_url).status_code == 200
    assert client.patch(detail_url, {"decision": "APPLY"}).status_code == 403
