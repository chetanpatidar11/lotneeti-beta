from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import User
from core.models import AuditEvent
from ipos.models import IPO
from ipos.providers import ManualIPOProvider


def payload():
    return {
        "issuer_name": "Synthetic Industries",
        "issue_type": "MAINBOARD",
        "lower_price": "100.00",
        "upper_price": "105.00",
        "lot_size": 140,
        "open_date": "2026-10-01",
        "close_date": "2026-10-03",
        "allotment_date": "2026-10-08",
        "listing_date": "2026-10-10",
        "source_url": "https://example.test/ipo/synthetic-001",
    }


def founder_session(client, founder):
    client.force_login(founder)
    session = client.session
    session["admin_mfa_verified"] = True
    session.save()


@pytest.mark.django_db
def test_founder_can_create_and_update_manual_ipo_with_provenance_and_audit():
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    client = Client()
    founder_session(client, founder)
    list_url = reverse("platform-ipo-list")

    created = client.post(list_url, data=payload(), content_type="application/json")
    assert created.status_code == 201
    data = created.json()
    assert data["source_key"] == "manual"
    assert data["source_record_id"]
    assert data["source_observed_at"]
    assert data["publication_state"] == "DRAFT"
    ipo = IPO.objects.get(pk=data["id"])
    observed_at = ipo.source_observed_at
    detail_url = reverse("platform-ipo-detail", args=[ipo.pk])

    edited = client.patch(
        detail_url,
        data={"upper_price": "108.00", "status": "OPEN", "publication_state": "PUBLISHED"},
        content_type="application/json",
    )
    assert edited.status_code == 200
    ipo.refresh_from_db()
    assert str(ipo.upper_price) == "108.00"
    assert ipo.source_record_id == data["source_record_id"]
    assert ipo.source_observed_at >= observed_at
    assert len(ipo.source_payload_hash) == 64
    assert AuditEvent.objects.filter(action="ipo.manual_created", actor=founder).count() == 1
    assert AuditEvent.objects.filter(action="ipo.manual_updated", actor=founder).count() == 1


@pytest.mark.django_db
def test_non_founder_and_founder_without_mfa_cannot_write_manual_ipo():
    owner = User.objects.create_user(email="owner@example.test")
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    client = Client()
    client.force_login(owner)
    assert (
        client.post(
            reverse("platform-ipo-list"), data=payload(), content_type="application/json"
        ).status_code
        == 403
    )
    client.force_login(founder)
    assert (
        client.post(
            reverse("platform-ipo-list"), data=payload(), content_type="application/json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_manual_provider_cannot_edit_other_source_and_rejects_invalid_dates():
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    client = Client()
    founder_session(client, founder)
    bad = payload() | {"close_date": "2026-09-30"}
    assert (
        client.post(
            reverse("platform-ipo-list"), data=bad, content_type="application/json"
        ).status_code
        == 400
    )

    ipo = IPO(
        issuer_name="External Synthetic",
        issue_type="MAINBOARD",
        lower_price="100.00",
        upper_price="105.00",
        lot_size=140,
        open_date=date(2026, 10, 1),
        close_date=date(2026, 10, 3),
        allotment_date=date(2026, 10, 8),
        source_key="synthetic-fixture",
        source_record_id="external-001",
    )
    ipo.save()
    with pytest.raises(ValueError):
        ManualIPOProvider().update(ipo, {"issuer_name": "Hijacked"})
    assert (
        client.patch(
            reverse("platform-ipo-detail", args=[ipo.pk]),
            data={"issuer_name": "Hijacked"},
            content_type="application/json",
        ).status_code
        == 404
    )
