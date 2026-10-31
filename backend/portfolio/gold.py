"""Physical gold records and exact lot-based calculations; no bank writes."""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Workspace, WorkspaceMembership
from core.audit import record_event
from portfolio.gold_prices import item_price, market_quote
from portfolio.models import GoldPurchase, GoldSale

MONEY = Decimal("0.01")
ZERO = Decimal("0")
PURCHASE_FIELDS = (
    "price_mode",
    "name",
    "form",
    "owner_name",
    "purity",
    "purchased_on",
    "grams",
    "total_cost",
    "current_price_per_gram",
    "seller",
    "notes",
)
SALE_FIELDS = ("sold_on", "grams", "net_proceeds", "notes")


def money(value):
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def writer(workspace, actor):
    if not WorkspaceMembership.objects.filter(
        workspace=workspace, user=actor, role__in=["OWNER", "OPERATOR"]
    ).exists():
        raise ValidationError("Only owners and operators can update gold records.")


def validate_purchase(item):
    item.full_clean()
    if item.purchased_on > timezone.localdate():
        raise ValidationError("Purchase date cannot be in the future.")
    active = (
        item.gold_sales.filter(voided_at__isnull=True)
        if item.pk and not item._state.adding
        else GoldSale.objects.none()
    )
    if (active.aggregate(total=Sum("grams"))["total"] or ZERO) > item.grams:
        raise ValidationError("Purchased grams cannot be less than the grams already sold.")
    if active.filter(sold_on__lt=item.purchased_on).exists():
        raise ValidationError("Purchase date cannot be after a recorded sale.")


def validate_sale(item, purchase):
    item.full_clean()
    if purchase.voided_at:
        raise ValidationError("Restore the purchase before adding or restoring a sale.")
    if item.sold_on < purchase.purchased_on or item.sold_on > timezone.localdate():
        raise ValidationError("Sale date must be on or after purchase and no later than today.")
    other = purchase.gold_sales.filter(voided_at__isnull=True).exclude(pk=item.pk)
    sold = other.aggregate(total=Sum("grams"))["total"] or ZERO
    if item.grams + sold > purchase.grams:
        raise ValidationError("Sale grams exceed the gold remaining in this purchase.")


@transaction.atomic
def create_purchase(*, workspace, actor, request_id, data):
    writer(workspace, actor)
    Workspace.objects.select_for_update().get(pk=workspace.pk)
    existing = GoldPurchase.objects.filter(workspace=workspace, request_id=request_id).first()
    if existing:
        if any(getattr(existing, field) != data[field] for field in PURCHASE_FIELDS):
            raise ValidationError(
                "This purchase request was already saved. Refresh Gold before trying again."
            )
        return existing, False
    item = GoldPurchase(workspace=workspace, created_by=actor, request_id=request_id, **data)
    if item.current_price_per_gram is not None:
        item.price_updated_at = timezone.now()
    validate_purchase(item)
    item.save()
    record_event(action="gold.purchase_created", target=item, actor=actor, workspace=workspace)
    return item, True


@transaction.atomic
def update_purchase(*, purchase, actor, data):
    item = GoldPurchase.objects.select_for_update().get(pk=purchase.pk)
    writer(item.workspace, actor)
    if item.voided_at:
        raise ValidationError("Restore the purchase before editing it.")
    before = {
        "grams_before": str(item.grams),
        "cost_before": str(item.total_cost),
        "price_mode_before": item.price_mode,
    }
    price_changed = item.current_price_per_gram != data["current_price_per_gram"]
    for field in PURCHASE_FIELDS:
        setattr(item, field, data[field])
    if price_changed:
        item.price_updated_at = timezone.now() if item.current_price_per_gram is not None else None
    validate_purchase(item)
    item.save()
    record_event(
        action="gold.purchase_edited",
        target=item,
        actor=actor,
        workspace=item.workspace,
        metadata={
            **before,
            "grams_after": str(item.grams),
            "cost_after": str(item.total_cost),
            "price_mode_after": item.price_mode,
        },
    )
    return item


@transaction.atomic
def save_sale(*, purchase, actor, data, request_id=None, sale=None):
    parent = GoldPurchase.objects.select_for_update().get(pk=purchase.pk)
    writer(parent.workspace, actor)
    if sale is None:
        existing = GoldSale.objects.filter(purchase=parent, request_id=request_id).first()
        if existing:
            if any(getattr(existing, field) != data[field] for field in SALE_FIELDS):
                raise ValidationError(
                    "This sale request was already saved. Refresh Gold before trying again."
                )
            return existing, False
        item = GoldSale(purchase=parent, created_by=actor, request_id=request_id, **data)
    else:
        item = GoldSale.objects.select_for_update().get(pk=sale.pk, purchase=parent)
        if item.voided_at:
            raise ValidationError("Restore this sale before editing it.")
        for field in SALE_FIELDS:
            setattr(item, field, data[field])
    validate_sale(item, parent)
    item.save()
    record_event(
        action="gold.sale_created" if sale is None else "gold.sale_edited",
        target=item,
        actor=actor,
        workspace=parent.workspace,
    )
    return item, sale is None


@transaction.atomic
def set_removed(*, purchase, actor, removed, sale=None):
    parent = GoldPurchase.objects.select_for_update().get(pk=purchase.pk)
    writer(parent.workspace, actor)
    item = GoldSale.objects.select_for_update().get(pk=sale.pk, purchase=parent) if sale else parent
    if sale is None and removed and parent.gold_sales.filter(voided_at__isnull=True).exists():
        raise ValidationError("Remove this purchase's recorded sales first, or edit the purchase.")
    if sale and not removed:
        validate_sale(item, parent)
    if bool(item.voided_at) == removed:
        return item
    item.voided_at = timezone.now() if removed else None
    item.save(update_fields=["voided_at", "updated_at"])
    record_event(
        action="gold.record_removed" if removed else "gold.record_restored",
        target=item,
        actor=actor,
        workspace=parent.workspace,
    )
    return item


def gold_report(workspace):
    market = market_quote()
    purchases = list(
        GoldPurchase.objects.filter(workspace=workspace).prefetch_related("gold_sales")
    )
    purchase_rows, sale_rows = [], []
    grams_held = remaining_cost = total_paid = net_receipts = realized = valued = ZERO
    missing_prices = active_count = 0
    for item in purchases:
        sold_grams = allocated = ZERO
        sales = sorted(
            item.gold_sales.all(), key=lambda sale: (sale.sold_on, sale.created_at, str(sale.pk))
        )
        for sale in sales:
            cost = profit = None
            if not sale.voided_at and not item.voided_at:
                cumulative_cost = money(item.total_cost * (sold_grams + sale.grams) / item.grams)
                cost = cumulative_cost - allocated
                sold_grams += sale.grams
                allocated = cumulative_cost
                profit = sale.net_proceeds - cost
                net_receipts += sale.net_proceeds
                realized += profit
            sale_rows.append(
                {
                    "id": str(sale.pk),
                    "purchase": str(item.pk),
                    "name": item.name,
                    "owner_name": item.owner_name,
                    "purity": item.purity,
                    "sold_on": sale.sold_on,
                    "grams": str(sale.grams),
                    "net_proceeds": str(sale.net_proceeds),
                    "allocated_cost": str(cost) if cost is not None else None,
                    "realized_profit": str(profit) if profit is not None else None,
                    "notes": sale.notes,
                    "removed": sale.voided_at is not None,
                }
            )
        remaining = item.grams - sold_grams
        cost_held = item.total_cost - allocated
        price, price_source, price_as_of = item_price(item, market)
        value = money(remaining * price) if price is not None else None
        if remaining == 0:
            value = ZERO
        pnl = value - cost_held if value is not None else None
        if not item.voided_at:
            active_count += 1
            total_paid += item.total_cost
            grams_held += remaining
            remaining_cost += cost_held
            if remaining > 0 and value is None:
                missing_prices += 1
            if value is not None:
                valued += value
        purchase_rows.append(
            {
                "id": str(item.pk),
                "name": item.name,
                "form": item.form,
                "owner_name": item.owner_name,
                "purity": item.purity,
                "purchased_on": item.purchased_on,
                "grams": str(item.grams),
                "total_cost": str(item.total_cost),
                "sold_grams": str(sold_grams),
                "remaining_grams": str(remaining),
                "remaining_cost": str(cost_held),
                "price_mode": item.price_mode,
                "effective_price_per_gram": str(price) if price is not None else None,
                "price_source": price_source,
                "price_as_of": price_as_of,
                "current_price_per_gram": str(item.current_price_per_gram)
                if item.current_price_per_gram is not None
                else None,
                "price_updated_at": item.price_updated_at,
                "estimated_value": str(value) if value is not None else None,
                "unrealized_profit": str(pnl) if pnl is not None else None,
                "seller": item.seller,
                "notes": item.notes,
                "removed": item.voided_at is not None,
            }
        )
    sale_rows.sort(key=lambda sale: (str(sale["sold_on"]), sale["id"]), reverse=True)
    return {
        "market": market,
        "purchases": purchase_rows,
        "sales": sale_rows,
        "summary": {
            "purchase_count": active_count,
            "grams_held": str(grams_held),
            "cost_of_holdings": str(remaining_cost),
            "total_paid": str(total_paid),
            "net_sale_receipts": str(net_receipts),
            "realized_profit": str(realized),
            "estimated_value": str(valued) if missing_prices == 0 else None,
            "unrealized_profit": str(valued - remaining_cost) if missing_prices == 0 else None,
            "priced_value": str(valued),
            "unpriced_holdings": missing_prices,
        },
    }
