from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import User
from ipos.models import IPO
from ipos.overrides import published_ipos


@pytest.mark.django_db
def test_dashboard_sync_requires_founder_mfa_and_coalesces_clicks():
    cache.clear()
    owner = User.objects.create_user(email="owner@example.test", password="test-password")
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    client = Client()
    url = reverse("ipo-live-sync")

    client.force_login(owner)
    assert client.get(url).json()["can_sync"] is False
    assert client.post(url, data={}, content_type="application/json").status_code == 403

    client.force_login(founder)
    assert client.get(url).json()["can_sync"] is False
    assert client.post(url, data={}, content_type="application/json").status_code == 403
    session = client.session
    session["admin_mfa_verified"] = True
    session.save()

    with patch(
        "ipos.public_views.run_ipo_sync",
        return_value={"investorgain": {"status": "OK", "imported": 2}},
    ) as sync:
        assert client.get(url).json()["can_sync"] is True
        assert (
            client.post(url, data={}, content_type="application/json").json()["result"]["imported"]
            == 2
        )
        assert client.post(url, data={}, content_type="application/json").status_code == 429
        sync.assert_called_once_with(provider="investorgain", manual=True)
    cache.clear()


@pytest.mark.django_db
def test_active_provider_keeps_legacy_exchange_records_out_of_customer_planning():
    base = {
        "issuer_name": "Synthetic Issue",
        "issue_type": "MAINBOARD",
        "lower_price": "100",
        "upper_price": "105",
        "lot_size": 100,
        "open_date": "2026-10-11",
        "close_date": "2026-10-13",
        "allotment_date": "2026-10-16",
        "status": "UPCOMING",
        "publication_state": "PUBLISHED",
    }
    IPO.objects.create(**base, source_key="nse", source_record_id="legacy")
    current = IPO.objects.create(**base, source_key="investorgain", source_record_id="current")
    with override_settings(ACTIVE_IPO_SOURCE="investorgain"):
        assert list(published_ipos()) == [current]
        preview = Client().get(reverse("market-ipo-preview"))
        assert preview.status_code == 200
        assert len(preview.json()["issues"]) == 1
        assert preview.json()["issues"][0]["issuer_name"] == "Synthetic Issue"
        assert "source_record_id" not in preview.json()["issues"][0]
