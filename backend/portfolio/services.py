"""Workspace-authorized, quantity-safe sale recording."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from accounts.models import WorkspaceMembership
from applications.models import Application
from core.audit import record_event
from core.beta_events import record_beta_event
from core.models import BetaEvent
from portfolio.models import Sale


@transaction.atomic
def record_sale(
    *,
    application: Application,
    actor,
    quantity: int,
    price_per_share: Decimal,
    sold_on: date,
    charges: Decimal = Decimal("0.00"),
) -> Sale:
    item = Application.objects.select_for_update().get(pk=application.pk)
    if not WorkspaceMembership.objects.filter(
        workspace_id=item.workspace_id,
        user=actor,
        role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
    ).exists():
        raise ValidationError("This member cannot record sales")
    if item.status != Application.Status.ALLOTTED or item.allotted_quantity is None:
        raise ValidationError("Only allotted shares can be sold")
    already_sold = item.sales.aggregate(total=Sum("quantity"))["total"] or 0
    if (
        type(quantity) is not int
        or quantity < 1
        or quantity > item.allotted_quantity - already_sold
    ):
        raise ValidationError("Sale quantity exceeds remaining allotted shares")
    if price_per_share <= 0 or charges < 0:
        raise ValidationError("Sale price must be positive and charges cannot be negative")
    sale = Sale.objects.create(
        application=item,
        quantity=quantity,
        price_per_share=price_per_share,
        sold_on=sold_on,
        charges=charges,
        actor=actor,
    )
    record_event(
        action="portfolio.sale_recorded",
        target=sale,
        actor=actor,
        workspace=item.workspace,
        metadata={
            "quantity": quantity,
            "price_per_share": str(price_per_share),
            "charges": str(charges),
        },
    )
    record_beta_event(workspace=item.workspace, event_type=BetaEvent.Type.PNL_COMPLETED)
    return sale
