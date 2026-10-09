from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from ipos.models import IPO, GMPObservation


def make_ipo(publication_state):
    return IPO.objects.create(
        issuer_name="Synthetic Industries",
        issue_type="MAINBOARD",
        lower_price=Decimal("100.00"),
        upper_price=Decimal("105.00"),
        lot_size=140,
        open_date=date(2026, 10, 1),
        close_date=date(2026, 10, 3),
        allotment_date=date(2026, 10, 8),
        publication_state=publication_state,
        source_key="synthetic-fixture",
        source_record_id=f"synthetic-{publication_state}",
    )


@pytest.mark.django_db
def test_published_ipo_exposes_current_gmp_and_timestamped_history():
    user = User.objects.create_user(email="member@example.test")
    published = make_ipo(IPO.PublicationState.PUBLISHED)
    draft = make_ipo(IPO.PublicationState.DRAFT)
    GMPObservation.objects.create(
        ipo=published,
        source_key="synthetic",
        value_per_share=Decimal("10.00"),
        observed_at=timezone.now() - timedelta(hours=2),
    )
    GMPObservation.objects.create(
        ipo=published,
        source_key="synthetic",
        value_per_share=Decimal("20.00"),
        observed_at=timezone.now() - timedelta(hours=1),
    )
    client = APIClient()
    client.force_authenticate(user)
    rows = client.get(reverse("ipo-list")).data
    assert len(rows) == 1
    assert rows[0]["id"] == str(published.pk)
    assert rows[0]["current_gmp"] == "20.00"
    assert rows[0]["current_gmp_percent"] == "19.05"
    history = client.get(reverse("ipo-gmp-history", args=[published.pk])).data
    assert [row["value_per_share"] for row in history] == ["20.00", "10.00"]
    assert [row["percent"] for row in history] == ["19.05", "9.52"]
    assert client.get(reverse("ipo-detail", args=[draft.pk])).status_code == 404
    assert client.get(reverse("ipo-gmp-history", args=[draft.pk])).status_code == 404


@pytest.mark.django_db
def test_gmp_public_api_requires_login_and_handles_missing_observation():
    ipo = make_ipo(IPO.PublicationState.PUBLISHED)
    client = APIClient()
    assert client.get(reverse("ipo-list")).status_code == 403
    user = User.objects.create_user(email="member@example.test")
    client.force_authenticate(user)
    detail = client.get(reverse("ipo-detail", args=[ipo.pk]))
    assert detail.data["current_gmp"] is None
    assert detail.data["current_gmp_percent"] is None
    assert client.get(reverse("ipo-gmp-history", args=[ipo.pk])).data == []
