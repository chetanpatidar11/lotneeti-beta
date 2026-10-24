"""Current quota and funding rules for new tracking/submission/edit actions."""

from decimal import Decimal

from django.core.exceptions import ValidationError

from ipos.models import IPOUserDecision
from ipos.quota_terms import confirmed_shareholder_quota, shareholder_terms_fingerprint


def shareholder_eligible(*, workspace, ipo, applicant_id):
    return bool(
        confirmed_shareholder_quota(ipo)
        and IPOUserDecision.objects.filter(
            workspace=workspace,
            ipo=ipo,
            shareholder_eligible__pk=applicant_id,
            shareholder_terms_fingerprint=shareholder_terms_fingerprint(ipo),
            shareholder_eligible__active=True,
            shareholder_eligible__is_deleted=False,
        ).exists()
    )


def validate_quota_mapping(*, workspace, ipo, applicant_id, category, lots, amount, bank, upi):
    if category == "SHARE":
        if not shareholder_eligible(workspace=workspace, ipo=ipo, applicant_id=applicant_id):
            raise ValidationError(
                "This investor is not confirmed eligible for this IPO's shareholder quota"
            )
        if lots < ipo.shareholder_min_lots or amount > ipo.shareholder_max_amount:
            raise ValidationError("Shareholder amount or lots exceed this IPO's quota terms")
    if category == "BHNI":
        if amount <= Decimal("1000000"):
            raise ValidationError("bHNI requires a whole-lot amount above ₹10,00,000")
        if (
            upi is not None
            or bank.owner_id != applicant_id
            or not bank.active
            or bank.is_placeholder
            or bank.is_imported_reference
        ):
            raise ValidationError(
                "bHNI requires the applicant's own active bank ASBA account, without UPI"
            )
    elif upi is None:
        raise ValidationError("Select an active UPI linked to the funding bank")
