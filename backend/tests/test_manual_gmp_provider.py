from datetime import date
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import User
from core.models import AuditEvent
from ipos.models import IPO, GMPObservation


def make_ipo():
    return IPO.objects.create(
        issuer_name="Synthetic Industries",
        issue_type="MAINBOARD",
        lower_price=Decimal("100.00"),
        upper_price=Decimal("105.00"),
        lot_size=140,
        open_date=date(2026, 10, 1),
        close_date=date(2026, 10, 3),
        allotment_date=date(2026, 10, 8),
        source_key="manual",
        source_record_id="synthetic-001",
    )


@pytest.mark.django_db
def test_founder_records_timestamped_gmp_without_overwriting_history():
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    ipo = make_ipo()
    client = Client()
    client.force_login(founder)
    session = client.session
    session["admin_mfa_verified"] = True
    session.save()
    url = reverse("platform-gmp-list", args=[ipo.pk])

    first = client.post(
        url,
        data={
            "value_per_share": "20.00",
            "observed_at": "2026-09-25T10:00:00Z",
            "source_url": "https://example.test/gmp/first",
        },
        content_type="application/json",
    )
    second = client.post(
        url,
        data={"value_per_share": "-5.00", "observed_at": "2026-09-26T10:00:00Z"},
        content_type="application/json",
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["source_key"] == "manual"
    assert len(first.json()["source_payload_hash"]) == 64
    assert [row["value_per_share"] for row in client.get(url).json()] == ["-5.00", "20.00"]
    assert GMPObservation.objects.filter(ipo=ipo, recorded_by=founder).count() == 2
    assert AuditEvent.objects.filter(action="gmp.manual_recorded", actor=founder).count() == 2


@pytest.mark.django_db
def test_manual_gmp_requires_founder_mfa_and_valid_ipo():
    owner = User.objects.create_user(email="owner@example.test")
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    ipo = make_ipo()
    url = reverse("platform-gmp-list", args=[ipo.pk])
    data = {"value_per_share": "20.00", "observed_at": "2026-09-26T10:00:00Z"}
    client = Client()
    client.force_login(owner)
    assert client.post(url, data=data, content_type="application/json").status_code == 403
    client.force_login(founder)
    assert client.post(url, data=data, content_type="application/json").status_code == 403
    session = client.session
    session["admin_mfa_verified"] = True
    session.save()
    assert (
        client.post(
            reverse("platform-gmp-list", args=["00000000-0000-0000-0000-000000000001"]),
            data=data,
            content_type="application/json",
        ).status_code
        == 404
    )
