"""Founder-confirmed issue terms; provider updates do not overwrite these fields."""

import json
from hashlib import sha256

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from core.audit import record_event
from ipos.models import IPO


class ShareholderTermsForm(forms.ModelForm):
    reason = forms.CharField(max_length=500)

    class Meta:
        model = IPO
        fields = (
            "shareholder_quota",
            "shareholder_min_lots",
            "shareholder_max_amount",
            "shareholder_record_date",
            "shareholder_terms_url",
            "reason",
        )
        widgets = {"shareholder_record_date": forms.DateInput(attrs={"type": "date"})}


@transaction.atomic
def set_shareholder_terms(*, ipo, actor, data):
    current = IPO.objects.select_for_update().get(pk=ipo.pk)
    form = ShareholderTermsForm(data=data, instance=current)
    if not form.is_valid():
        raise ValidationError(
            [f"{key}: {value}" for key, values in form.errors.items() for value in values]
        )
    changed = form.save(commit=False)
    changed.save(
        update_fields=[name for name in ShareholderTermsForm.Meta.fields if name != "reason"]
        + ["updated_at"]
    )
    record_event(
        action="ipo.shareholder_terms_updated",
        target=changed,
        actor=actor,
        metadata={
            "enabled": changed.shareholder_quota,
            "reason": form.cleaned_data["reason"],
            "terms_url": changed.shareholder_terms_url,
        },
    )
    return changed


def shareholder_terms_fingerprint(ipo):
    values = [
        ipo.shareholder_quota,
        ipo.issue_type,
        ipo.shareholder_min_lots,
        str(ipo.shareholder_max_amount),
        str(ipo.shareholder_record_date),
        ipo.shareholder_terms_url,
    ]
    return sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def confirmed_shareholder_quota(ipo):
    if not ipo.shareholder_quota or not ipo.shareholder_terms_url:
        return False
    from ipos.overrides import effective_ipo_values

    return effective_ipo_values(ipo)["issue_type"] == "MAINBOARD"
