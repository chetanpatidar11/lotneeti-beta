from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from applications.models import Application
from core.models import AuditEvent
from planner.persistence import create_plan_run
from portfolio.models import Sale


@pytest.mark.django_db
def test_sale_records_partial_quantities_and_rejects_oversell():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk]), {})
    application = Application.objects.get()
    sale_url = reverse("sale-list", args=[workspace.pk])
    payload = {
        "application": str(application.pk),
        "quantity": 40,
        "price_per_share": "120.50",
        "sold_on": "2030-10-10",
        "charges": "45.25",
    }
    assert client.post(sale_url, payload, format="json").status_code == 409
    for action in ("submit", "block"):
        assert (
            client.post(
                reverse("application-action", args=[workspace.pk, application.pk, action]), {}
            ).status_code
            == 200
        )
    assert (
        client.post(
            reverse("application-action", args=[workspace.pk, application.pk, "allotted"]),
            {"quantity": 100, "actual_cost": "9900.00"},
            format="json",
        ).status_code
        == 200
    )
    first = client.post(sale_url, payload, format="json")
    assert first.status_code == 201
    assert first.data["charges"] == "45.25"
    assert first.data["gross_proceeds"] == "4820.00"
    assert first.data["ipo_cost"] == "3960.00"
    assert first.data["realized_profit"] == "814.75"
    assert first.data["roi_percent"] == "20.57"
    assert Sale.objects.get().price_per_share == Decimal("120.50")
    assert client.post(sale_url, {**payload, "quantity": 61}, format="json").status_code == 409
    second = client.post(sale_url, {**payload, "quantity": 60}, format="json")
    assert second.status_code == 201
    assert second.data["gross_proceeds"] == "7230.00"
    assert second.data["ipo_cost"] == "5940.00"
    assert second.data["realized_profit"] == "1244.75"
    assert second.data["roi_percent"] == "20.96"
    assert client.post(sale_url, {**payload, "quantity": 1}, format="json").status_code == 409
    listed = client.get(sale_url).data
    assert len(listed) == 2
    assert sum(Decimal(item["ipo_cost"]) for item in listed) == Decimal("9900.00")
    assert AuditEvent.objects.filter(action="portfolio.sale_recorded").count() == 2


@pytest.mark.django_db
def test_sale_input_and_workspace_access():
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
        {"quantity": 100, "actual_cost": "9900.00"},
        format="json",
    )
    url = reverse("sale-list", args=[workspace.pk])
    payload = {
        "application": str(application.pk),
        "quantity": 1,
        "price_per_share": "101.00",
        "sold_on": "2030-10-10",
    }
    assert client.post(url, {**payload, "price_per_share": "0"}, format="json").status_code == 400
    assert client.post(url, {**payload, "charges": "-1"}, format="json").status_code == 400
    viewer = User.objects.create_user(email="sale-viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert client.get(url).status_code == 200
    assert client.post(url, payload, format="json").status_code == 403
    outsider = User.objects.create_user(email="sale-outsider@example.test")
    client.force_authenticate(outsider)
    assert client.get(url).status_code == 404
    assert client.post(url, payload, format="json").status_code == 404
