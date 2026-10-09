from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from test_ipos import issue

from accounts.models import User
from core.models import AuditEvent
from ipos.models import IPOFieldOverride
from ipos.overrides import effective_ipo_values, resume_ipo_auto, set_ipo_override


@pytest.mark.django_db
def test_source_updates_do_not_replace_override_and_resume_restores_source():
    founder = User.objects.create_superuser(email="override@example.invalid", password="test")
    ipo = issue(source_key="manual")
    ipo.save()
    first = set_ipo_override(
        ipo=ipo, field_name="upper_price", value="120.00", reason="Corrected notice", actor=founder
    )
    assert ipo.upper_price == Decimal("105.00")
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("120.00")

    ipo.upper_price = Decimal("110.00")
    ipo.save()
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("120.00")
    second = set_ipo_override(
        ipo=ipo, field_name="upper_price", value="125.00", reason="New notice", actor=founder
    )
    first.refresh_from_db()
    assert first.resumed_at is not None
    assert first.resumed_by == founder
    assert second.resumed_at is None
    active = IPOFieldOverride.objects.filter(ipo=ipo, resumed_at__isnull=True)
    assert active.count() == 1
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("125.00")

    resume_ipo_auto(ipo=ipo, field_name="upper_price", actor=founder)
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("110.00")
    assert IPOFieldOverride.objects.filter(ipo=ipo, resumed_at__isnull=True).count() == 0
    events = AuditEvent.objects.filter(action__startswith="ipo.override_")
    assert list(events.values_list("action", flat=True)) == [
        "ipo.override_resumed",
        "ipo.override_set",
        "ipo.override_set",
    ]
    assert all(
        set(event.metadata) == {"field"}
        for event in AuditEvent.objects.filter(action__startswith="ipo.override_")
    )


@pytest.mark.django_db
def test_override_validates_field_reason_and_effective_issue_facts():
    founder = User.objects.create_superuser(email="override@example.invalid", password="test")
    ipo = issue()
    ipo.save()
    for field_name, value, reason in (
        ("source_key", "tampered", "reason"),
        ("upper_price", "120.00", ""),
        ("lower_price", "200.00", "reason"),
        ("lot_size", "0", "reason"),
    ):
        with pytest.raises(ValidationError):
            set_ipo_override(
                ipo=ipo, field_name=field_name, value=value, reason=reason, actor=founder
            )
    assert IPOFieldOverride.objects.count() == 0
    with pytest.raises(ValidationError):
        resume_ipo_auto(ipo=ipo, field_name="upper_price", actor=founder)


@pytest.mark.django_db
def test_resume_does_not_create_invalid_combined_effective_values():
    founder = User.objects.create_superuser(email="override@example.invalid", password="test")
    ipo = issue()
    ipo.save()
    set_ipo_override(
        ipo=ipo, field_name="upper_price", value="130.00", reason="New upper", actor=founder
    )
    set_ipo_override(
        ipo=ipo, field_name="lower_price", value="120.00", reason="New lower", actor=founder
    )
    with pytest.raises(ValidationError):
        resume_ipo_auto(ipo=ipo, field_name="upper_price", actor=founder)
    assert effective_ipo_values(ipo)["upper_price"] == Decimal("130.00")
    assert IPOFieldOverride.objects.filter(ipo=ipo, resumed_at__isnull=True).count() == 2
