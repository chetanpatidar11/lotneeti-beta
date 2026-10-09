from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User
from applications.models import Application
from planner.persistence import create_plan_run


@pytest.mark.django_db
def test_period_report_groups_actual_realized_results_without_reallocating_cost():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk]), {})
    application = Application.objects.get()
    for action in ("submit", "block"):
        client.post(reverse("application-action", args=[workspace.pk, application.pk, action]), {})
    client.post(
        reverse("application-action", args=[workspace.pk, application.pk, "allotted"]),
        {"quantity": 3, "actual_cost": "100.00"},
        format="json",
    )
    sale_url = reverse("sale-list", args=[workspace.pk])
    for sold_on in ("2030-10-10", "2030-11-10", "2030-11-11"):
        result = client.post(
            sale_url,
            {
                "application": str(application.pk),
                "quantity": 1,
                "price_per_share": "40.00",
                "sold_on": sold_on,
                "charges": "1.00",
            },
            format="json",
        )
        assert result.status_code == 201
    report_url = reverse("profit-report", args=[workspace.pk])
    whole = client.get(report_url).data
    assert whole["sale_count"] == 3
    assert whole["workspace"] == {
        "gross_proceeds": "120.00",
        "ipo_cost": "100.00",
        "charges": "3.00",
        "realized_profit": "17.00",
        "roi_percent": "17.00",
    }
    assert whole["by_ipo"][0]["realized_profit"] == "17.00"
    assert whole["by_investor"][0]["realized_profit"] == "17.00"
    november = client.get(report_url, {"from_date": "2030-11-01", "to_date": "2030-11-30"}).data
    assert november["sale_count"] == 2
    assert november["workspace"]["ipo_cost"] == "66.67"
    assert november["workspace"]["realized_profit"] == "11.33"
    assert Decimal(november["workspace"]["gross_proceeds"]) == Decimal("80.00")
    assert (
        client.get(report_url, {"from_date": "2030-12-01", "to_date": "2030-11-01"}).status_code
        == 400
    )
    outsider = User.objects.create_user(email="profit-outsider@example.test")
    client.force_authenticate(outsider)
    assert client.get(report_url).status_code == 404
