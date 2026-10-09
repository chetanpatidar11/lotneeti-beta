from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User
from applications.models import Application
from ipos.models import IPO
from planner.persistence import create_plan_run


@pytest.mark.django_db
def test_operations_cards_use_published_open_ipos_and_scoped_application_sale_state(monkeypatch):
    monkeypatch.setattr("applications.views.timezone.localdate", lambda: date(2026, 9, 30))
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("workspace-operations", args=[workspace.pk])
    initial = client.get(url)
    assert initial.data == {
        "active_ipos": 0,
        "applications": 0,
        "pending_mandates": 0,
        "allotment_wins": 0,
        "realized_gains": "0.00",
    }
    ipo = IPO.objects.get()
    today = timezone.localdate()
    ipo.open_date = today - timedelta(days=1)
    ipo.close_date = today + timedelta(days=1)
    ipo.allotment_date = today + timedelta(days=7)
    ipo.listing_date = today + timedelta(days=14)
    ipo.status = IPO.Status.OPEN
    ipo.save()
    assert client.get(url).data["active_ipos"] == 1
    client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk]), {})
    application = Application.objects.get()
    assert client.get(url).data["applications"] == 1
    client.post(reverse("application-action", args=[workspace.pk, application.pk, "submit"]), {})
    assert client.get(url).data["pending_mandates"] == 1
    client.post(reverse("application-action", args=[workspace.pk, application.pk, "block"]), {})
    assert client.get(url).data["pending_mandates"] == 0
    client.post(
        reverse("application-action", args=[workspace.pk, application.pk, "allotted"]),
        {"quantity": 100, "actual_cost": "10000.00"},
        format="json",
    )
    assert client.get(url).data["allotment_wins"] == 1
    sale = client.post(
        reverse("sale-list", args=[workspace.pk]),
        {
            "application": str(application.pk),
            "quantity": 100,
            "price_per_share": "110.00",
            "sold_on": str(today),
            "charges": "50.00",
        },
        format="json",
    )
    assert sale.status_code == 201
    assert client.get(url).data["realized_gains"] == "950.00"
    outsider = User.objects.create_user(email="operations-outsider@example.test")
    client.force_authenticate(outsider)
    assert client.get(url).status_code == 404
