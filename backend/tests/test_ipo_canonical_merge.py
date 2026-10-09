import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from core.models import AuditEvent
from ipos.canonical import resolve_canonical_ipo
from ipos.feed_ingest import (
    NormalizedExchangeIPOProvider,
    record_exchange_snapshot,
    set_canonical_source_enabled,
)
from ipos.models import IPO, IPOSourceLink, IPOSourceSnapshot
from ipos.overrides import effective_ipo_values, resume_ipo_auto, set_ipo_override


def make_ipo():
    return IPO.objects.create(
        issuer_name="Synthetic Industries",
        issue_type=IPO.IssueType.MAINBOARD,
        lower_price=Decimal("100.00"),
        upper_price=Decimal("105.00"),
        lot_size=140,
        open_date=date(2026, 10, 1),
        close_date=date(2026, 10, 3),
        allotment_date=date(2026, 10, 8),
        publication_state=IPO.PublicationState.PUBLISHED,
        source_key="manual",
        source_record_id="synthetic-001",
    )


def source_fields(**changes):
    return {
        "issuer_name": "Synthetic Industries",
        "symbol": "SYNTH",
        "issue_type": "MAINBOARD",
        "lower_price": "100.00",
        "upper_price": "105.00",
        "lot_size": 140,
        "open_date": "2026-10-01",
        "close_date": "2026-10-03",
        "allotment_date": "2026-10-08",
        "status": "OPEN",
        **changes,
    }


def add_source(ipo, key, actor, *, observed_at=None, approve=True, **changes):
    observed_at = observed_at or datetime(2026, 9, 28, 10, tzinfo=UTC)
    record = NormalizedExchangeIPOProvider(key).normalize(
        source_fields(**changes),
        source_record_id=f"{key}-synthetic-001",
        observed_at=observed_at,
    )
    snapshot = record_exchange_snapshot(ipo=ipo, record=record)
    if approve:
        set_canonical_source_enabled(
            link=snapshot.link,
            enabled=True,
            rights_reference="synthetic-fixture-test-only",
            actor=actor,
        )
    return snapshot


@pytest.mark.django_db
def test_unapproved_snapshot_stays_review_only_and_requires_documented_rights():
    ipo = make_ipo()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    snapshot = add_source(ipo, "nse", founder, approve=False, upper_price="110.00")
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("105.00")
    assert IPOSourceSnapshot.objects.count() == 1
    with pytest.raises(ValidationError, match="permission"):
        set_canonical_source_enabled(
            link=snapshot.link, enabled=True, rights_reference="", actor=founder
        )
    member = User.objects.create_user(email="member@example.test")
    with pytest.raises(ValidationError, match="Founder"):
        set_canonical_source_enabled(
            link=snapshot.link, enabled=True, rights_reference="synthetic", actor=member
        )


@pytest.mark.django_db
def test_approved_equal_exchange_values_keep_sebi_document_provenance():
    ipo = make_ipo()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    for source in ("nse", "bse", "sebi"):
        add_source(ipo, source, founder, upper_price="110.00")

    result = resolve_canonical_ipo(ipo)
    assert result.values["upper_price"] == Decimal("110.00")
    assert result.fields["upper_price"].selected_source == "nse"
    assert result.fields["upper_price"].provenance_source == "sebi"
    assert result.exchange_conflict_fields == ()
    assert result.fields["upper_price"].source_values == {
        "cached": Decimal("105.00"),
        "nse": Decimal("110.00"),
        "bse": Decimal("110.00"),
        "sebi": Decimal("110.00"),
    }
    assert ipo.upper_price == Decimal("105.00")

    api = APIClient()
    api.force_authenticate(founder)
    data = api.get(reverse("ipo-detail", args=[ipo.pk])).data
    assert data["upper_price"] == "110.00"
    assert "ipo_field_provenance" not in data
    assert "ipo_source_conflict_fields" not in data


@pytest.mark.django_db
@pytest.mark.parametrize("source", ["nse", "bse"])
def test_single_approved_exchange_value_precedes_cached_value(source):
    ipo = make_ipo()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    add_source(ipo, source, founder, upper_price="110.00")
    result = resolve_canonical_ipo(ipo)
    assert result.values["upper_price"] == Decimal("110.00")
    assert result.fields["upper_price"].selected_source == source


@pytest.mark.django_db
def test_document_disagreement_is_visible_without_changing_exchange_precedence():
    ipo = make_ipo()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    add_source(ipo, "nse", founder, upper_price="110.00")
    add_source(ipo, "sebi", founder, upper_price="108.00")
    result = resolve_canonical_ipo(ipo)
    assert result.values["upper_price"] == Decimal("110.00")
    assert result.document_disagreement_fields == ("upper_price",)
    assert result.fields["upper_price"].source_values["sebi"] == Decimal("108.00")


@pytest.mark.django_db
def test_optional_field_not_present_in_source_does_not_override_cached_status():
    ipo = make_ipo()
    ipo.status = IPO.Status.CLOSED
    ipo.save()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    raw = source_fields(upper_price="110.00")
    raw.pop("status")
    record = NormalizedExchangeIPOProvider("nse").normalize(
        raw,
        source_record_id="nse-synthetic-001",
        observed_at=datetime(2026, 9, 28, 10, tzinfo=UTC),
    )
    snapshot = record_exchange_snapshot(ipo=ipo, record=record)
    set_canonical_source_enabled(
        link=snapshot.link,
        enabled=True,
        rights_reference="synthetic-fixture-test-only",
        actor=founder,
    )
    assert effective_ipo_values(ipo)["status"] == IPO.Status.CLOSED
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("110.00")


@pytest.mark.django_db
def test_dual_exchange_conflict_keeps_cached_value_and_manual_override_wins():
    ipo = make_ipo()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    add_source(ipo, "nse", founder, upper_price="110.00")
    add_source(ipo, "bse", founder, upper_price="115.00")
    result = resolve_canonical_ipo(ipo)
    assert result.values["upper_price"] == Decimal("105.00")
    assert result.exchange_conflict_fields == ("upper_price",)
    assert result.fields["upper_price"].source_values["nse"] == Decimal("110.00")
    assert result.fields["upper_price"].source_values["bse"] == Decimal("115.00")

    set_ipo_override(
        ipo=ipo,
        field_name="upper_price",
        value="112.00",
        reason="Founder reviewed source conflict",
        actor=founder,
    )
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("112.00")
    resume_ipo_auto(ipo=ipo, field_name="upper_price", actor=founder)
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("105.00")

    api = APIClient()
    api.force_authenticate(founder)
    data = api.get(reverse("ipo-detail", args=[ipo.pk])).data
    assert "ipo_source_conflict_fields" not in data
    assert data["upper_price"] == "105.00"


@pytest.mark.django_db
def test_sebi_fallback_keeps_last_value_without_new_snapshot_and_disable_uses_cache():
    ipo = make_ipo()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    add_source(ipo, "sebi", founder, upper_price="108.00")
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("108.00")
    # A failed fetch inserts no replacement snapshot and cannot clear the last value.
    assert IPOSourceSnapshot.objects.count() == 1
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("108.00")
    link = IPOSourceLink.objects.get(source_key="sebi")
    set_canonical_source_enabled(
        link=link, enabled=False, rights_reference="provider unavailable", actor=founder
    )
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("105.00")
    assert IPO.objects.get(pk=ipo.pk).upper_price == Decimal("105.00")
    assert AuditEvent.objects.filter(action="ipo.source_canonical_disabled").count() == 1


@pytest.mark.django_db
def test_invalid_combination_of_source_facts_falls_back_to_valid_cached_issue():
    ipo = make_ipo()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    add_source(ipo, "nse", founder, lower_price="110.00", upper_price="120.00")
    add_source(ipo, "bse", founder, lower_price="110.00", upper_price="125.00")
    result = resolve_canonical_ipo(ipo)
    assert result.validation_blocked is True
    assert result.values["lower_price"] == Decimal("100.00")
    assert result.values["upper_price"] == Decimal("105.00")
    assert result.exchange_conflict_fields == ("upper_price",)


@pytest.mark.django_db
def test_latest_approved_snapshot_is_used_without_deleting_old_observations():
    ipo = make_ipo()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    first_time = datetime(2026, 9, 28, 10, tzinfo=UTC)
    add_source(ipo, "nse", founder, observed_at=first_time, upper_price="110.00")
    add_source(
        ipo,
        "nse",
        founder,
        observed_at=first_time + timedelta(hours=1),
        upper_price="111.00",
    )
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("111.00")
    assert IPOSourceSnapshot.objects.count() == 2


@pytest.mark.django_db
def test_founder_exception_and_source_review_show_both_conflicting_values():
    ipo = make_ipo()
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    add_source(ipo, "nse", founder, upper_price="110.00")
    add_source(ipo, "bse", founder, upper_price="115.00")
    site = Client()
    site.force_login(founder)
    session = site.session
    session["admin_mfa_verified"] = True
    session.save()
    exceptions = site.get(reverse("founder_admin:ipo-exceptions"))
    detail = site.get(reverse("founder_admin:ipo-override-detail", args=[ipo.pk]))
    assert b"IPO source conflict: upper_price" in exceptions.content
    assert b"NSE: 110.00" in detail.content
    assert b"BSE: 115.00" in detail.content
    assert b"Exchange values differ" in detail.content


@pytest.mark.django_db
def test_file_import_stages_normalized_record_without_promoting_it(tmp_path):
    ipo = make_ipo()
    source_file = tmp_path / "synthetic-issue.json"
    source_file.write_text(json.dumps(source_fields(upper_price="110.00")))
    output = StringIO()
    call_command(
        "import_ipo_snapshot",
        ipo_id=str(ipo.pk),
        source="nse",
        record_id="nse-synthetic-001",
        observed_at="2026-09-28T10:00:00+00:00",
        file=str(source_file),
        stdout=output,
    )
    assert "canonical IPO unchanged" in output.getvalue()
    assert IPOSourceSnapshot.objects.count() == 1
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("105.00")
