from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from applications.models import Application
from funding.models import BalanceChange
from ipos.models import IPO
from ipos.overrides import set_ipo_override
from planner.persistence import create_plan_run


@pytest.mark.django_db
@pytest.mark.parametrize("cost", ["7300.73", "7200.00"])
def test_saved_tracked_and_updated_applications_expose_effective_upper_price_for_results(cost):
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    ipo = run.rows.get().ipo_ref
    set_ipo_override(
        ipo=IPO.objects.get(pk=ipo),
        field_name="upper_price",
        value="100.01",
        reason="Synthetic corrected upper band",
        actor=owner,
    )
    client = APIClient()
    client.force_authenticate(owner)
    listed = client.get(reverse("application-list", args=[workspace.pk]))
    assert listed.status_code == 200 and listed.data[0]["upper_price"] == "100.01"
    assert listed.data[0]["lot_size"] == 150
    tracked = client.post(
        reverse("application-start-tracking", args=[workspace.pk, run.pk]),
        {"record_only": True},
        format="json",
    )
    assert tracked.status_code == 201 and tracked.data[0]["upper_price"] == "100.01"
    assert tracked.data[0]["lot_size"] == 150
    item = Application.objects.get()
    assert (
        client.get(reverse("application-list", args=[workspace.pk])).data[0]["upper_price"]
        == "100.01"
    )
    blocked = client.post(
        reverse("application-bulk", args=[workspace.pk]),
        {"action": "block", "ids": [str(item.pk)], "record_only": True},
        format="json",
    )
    assert blocked.status_code == 200 and blocked.data[0]["upper_price"] == "100.01"
    result_url = reverse("application-action", args=[workspace.pk, item.pk, "allotted"])
    # The website defaults to upper-band cost; the user may edit that amount.
    recorded = client.post(result_url, {"quantity": 73, "actual_cost": cost}, format="json")
    assert recorded.status_code == 200 and recorded.data["upper_price"] == "100.01"
    assert recorded.data["allotted_quantity"] == 73
    assert recorded.data["actual_cost"] == cost
    assert recorded.data["lot_size"] == 150
    item.bank.refresh_from_db()
    assert item.bank.current_balance == Decimal("50000.00") - Decimal(cost)
    assert BalanceChange.objects.filter(operation="ALLOTMENT").count() == 1
    assert (
        client.post(result_url, {"quantity": 73, "actual_cost": cost}, format="json").status_code
        == 409
    )
    assert BalanceChange.objects.filter(operation="ALLOTMENT").count() == 1
