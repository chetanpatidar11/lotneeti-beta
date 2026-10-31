import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from applications.models import Application
from core.models import AuditEvent
from funding.models import BalanceChange, BankAccount
from portfolio.models import GoldPurchase, GoldSale, Sale


@pytest.fixture
def gold():
    owner, workspace, _ = setup_plan()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("gold-list", args=[workspace.pk])
    payload = {
        "request_id": str(uuid.uuid4()),
        "name": "Synthetic gold coin",
        "form": "COIN",
        "owner_name": "Synthetic Owner",
        "purity": "24K / 999",
        "grams": "10.000000",
        "total_cost": "60000.00",
        "purchased_on": str(timezone.localdate() - timedelta(days=30)),
        "current_price_per_gram": "7000.00",
        "seller": "Synthetic seller",
        "notes": "Synthetic fixture",
    }
    return owner, workspace, client, url, payload


def create(gold, **changed):
    _, _, client, url, payload = gold
    response = client.post(url, payload | changed, format="json")
    assert response.status_code == 201, response.data
    return response.data["purchases"][0]


def sale_data(purchase, **changed):
    return {
        "request_id": str(uuid.uuid4()),
        "purchase": purchase["id"],
        "sold_on": str(timezone.localdate() - timedelta(days=5)),
        "grams": "2.500000",
        "net_proceeds": "18000.00",
        "notes": "Synthetic partial sale",
        **changed,
    }


@pytest.mark.django_db
def test_gold_purchases_sales_values_and_edits_do_not_change_ipo_money(gold):
    _, workspace, client, url, payload = gold
    balances = list(BankAccount.objects.values_list("pk", "current_balance"))
    purchase = create(gold)
    assert purchase["estimated_value"] == "70000.00"
    assert purchase["unrealized_profit"] == "10000.00"
    sale_url = reverse("gold-sale-list", args=[workspace.pk])
    response = client.post(sale_url, sale_data(purchase), format="json")
    assert response.status_code == 201
    row = response.data["purchases"][0]
    assert Decimal(row["remaining_grams"]) == Decimal("7.5")
    assert row["remaining_cost"] == "45000.00" and row["estimated_value"] == "52500.00"
    assert row["unrealized_profit"] == "7500.00"
    assert response.data["sales"][0]["realized_profit"] == "3000.00"
    edit = reverse("gold-purchase", args=[workspace.pk, purchase["id"]])
    response = client.patch(edit, payload | {"total_cost": "65000.00"}, format="json")
    assert response.status_code == 200
    assert response.data["sales"][0]["allocated_cost"] == "16250.00"
    assert response.data["summary"]["realized_profit"] == "1750.00"
    assert list(BankAccount.objects.values_list("pk", "current_balance")) == balances
    assert (
        not BalanceChange.objects.exists()
        and not Application.objects.exists()
        and not Sale.objects.exists()
    )
    assert AuditEvent.objects.filter(action__startswith="gold.").count() == 3
    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
def test_gold_missing_quote_is_unknown_instead_of_zero_profit(gold):
    _, _, client, url, _ = gold
    create(gold, current_price_per_gram=None)
    summary = client.get(url).data["summary"]
    assert summary["unpriced_holdings"] == 1
    assert summary["estimated_value"] is None and summary["unrealized_profit"] is None
    assert summary["cost_of_holdings"] == "60000.00"


@pytest.mark.django_db
def test_full_fractional_sales_allocate_every_paisa_exactly_and_allow_backdating(gold):
    _, workspace, client, url, _ = gold
    purchase = create(gold, grams="0.000003", total_cost="0.05", current_price_per_gram=None)
    sale_url = reverse("gold-sale-list", args=[workspace.pk])
    for days in [3, 1, 2]:
        response = client.post(
            sale_url,
            sale_data(
                purchase,
                grams="0.000001",
                net_proceeds="0.03",
                sold_on=str(timezone.localdate() - timedelta(days=days)),
            ),
            format="json",
        )
        assert response.status_code == 201, response.data
    result = client.get(url).data
    assert sum(Decimal(row["allocated_cost"]) for row in result["sales"]) == Decimal("0.05")
    assert result["summary"]["cost_of_holdings"] == "0.00"
    assert Decimal(result["summary"]["grams_held"]) == 0
    assert Decimal(result["summary"]["realized_profit"]) == Decimal("0.04")
    assert Decimal(result["summary"]["estimated_value"]) == 0
    assert result["summary"]["unpriced_holdings"] == 0
    assert (
        client.post(sale_url, sale_data(purchase, grams="0.000001"), format="json").status_code
        == 409
    )


@pytest.mark.django_db
def test_gold_retry_ids_prevent_duplicate_purchases_and_sales(gold):
    _, workspace, client, url, payload = gold
    purchase = create(gold)
    assert client.post(url, payload, format="json").status_code == 200
    assert GoldPurchase.objects.count() == 1
    assert client.post(url, payload | {"grams": "11"}, format="json").status_code == 409
    data = sale_data(purchase)
    sale_url = reverse("gold-sale-list", args=[workspace.pk])
    assert client.post(sale_url, data, format="json").status_code == 201
    assert client.post(sale_url, data, format="json").status_code == 200
    assert GoldSale.objects.count() == 1
    assert client.post(sale_url, data | {"net_proceeds": "19000"}, format="json").status_code == 409


@pytest.mark.django_db
def test_gold_sales_can_be_edited_removed_restored_and_cannot_orphan_a_purchase(gold):
    _, workspace, client, url, _ = gold
    purchase = create(gold)
    purchase_url = reverse("gold-purchase", args=[workspace.pk, purchase["id"]])
    sale = client.post(
        reverse("gold-sale-list", args=[workspace.pk]), sale_data(purchase), format="json"
    ).data["sales"][0]
    sale_url = reverse("gold-sale", args=[workspace.pk, sale["id"]])
    assert client.delete(purchase_url).status_code == 409
    update = {
        "sold_on": sale["sold_on"],
        "grams": "5",
        "net_proceeds": "34000",
        "notes": "Corrected synthetic sale",
    }
    changed = client.patch(sale_url, update, format="json")
    assert changed.status_code == 200 and changed.data["summary"]["realized_profit"] == "4000.00"
    removed = client.delete(sale_url)
    assert removed.status_code == 200 and Decimal(removed.data["summary"]["grams_held"]) == 10
    assert removed.data["sales"][0]["removed"]
    assert client.delete(purchase_url).status_code == 200
    assert client.post(sale_url, {}, format="json").status_code == 409
    assert client.post(purchase_url, {}, format="json").status_code == 200
    assert client.post(sale_url, {}, format="json").status_code == 200
    result = client.get(url).data
    assert Decimal(result["summary"]["grams_held"]) == 5
    assert result["summary"]["realized_profit"] == "4000.00"
    assert GoldPurchase.objects.count() == 1 and GoldSale.objects.count() == 1


@pytest.mark.django_db
def test_gold_validation_dates_precision_and_edit_bounds(gold):
    _, workspace, client, url, payload = gold
    for changed in [
        {"grams": "0"},
        {"grams": "0.0000001"},
        {"total_cost": "-1"},
        {"current_price_per_gram": "0"},
        {"purity": ""},
        {"name": " "},
        {"form": "DIGITAL"},
    ]:
        assert client.post(url, payload | changed, format="json").status_code == 400
    assert (
        client.post(
            url,
            payload | {"purchased_on": str(timezone.localdate() + timedelta(days=1))},
            format="json",
        ).status_code
        == 409
    )
    purchase = create(gold)
    sale_url = reverse("gold-sale-list", args=[workspace.pk])
    for changed in [
        {"grams": "11"},
        {"sold_on": str(timezone.localdate() - timedelta(days=31))},
        {"sold_on": str(timezone.localdate() + timedelta(days=1))},
    ]:
        assert (
            client.post(sale_url, sale_data(purchase, **changed), format="json").status_code == 409
        )
    assert client.post(sale_url, sale_data(purchase), format="json").status_code == 201
    edit_url = reverse("gold-purchase", args=[workspace.pk, purchase["id"]])
    assert client.patch(edit_url, payload | {"grams": "2"}, format="json").status_code == 409
    assert (
        client.patch(
            edit_url, payload | {"purchased_on": str(timezone.localdate())}, format="json"
        ).status_code
        == 409
    )
    assert GoldPurchase.objects.get().grams == 10


@pytest.mark.django_db
def test_gold_membership_read_only_and_foreign_object_denial(gold):
    _, workspace, client, url, payload = gold
    purchase = create(gold)
    sale_url = reverse("gold-sale-list", args=[workspace.pk])
    sale = client.post(sale_url, sale_data(purchase), format="json").data["sales"][0]
    purchase_url = reverse("gold-purchase", args=[workspace.pk, purchase["id"]])
    sale_item_url = reverse("gold-sale", args=[workspace.pk, sale["id"]])
    viewer = User.objects.create_user(email="gold-viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert client.get(url).status_code == 200
    assert client.post(url, payload, format="json").status_code == 403
    for target in [purchase_url, sale_item_url]:
        assert client.patch(target, {}, format="json").status_code == 403
        assert client.delete(target).status_code == 403
        assert client.post(target, {}, format="json").status_code == 403
    outsider = User.objects.create_user(email="gold-outsider@example.test")
    client.force_authenticate(outsider)
    assert client.get(url).status_code == 404
    assert client.post(sale_url, sale_data(purchase), format="json").status_code == 404
    client.force_authenticate(None)
    assert client.get(url).status_code in {401, 403}


@pytest.mark.django_db
def test_gold_operator_writes_and_record_ids_cannot_cross_member_scopes(gold):
    owner, workspace, client, url, payload = gold
    operator = User.objects.create_user(email="gold-operator@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=operator, role="OPERATOR")
    client.force_authenticate(operator)
    purchase = create(gold)
    sale = client.post(
        reverse("gold-sale-list", args=[workspace.pk]), sale_data(purchase), format="json"
    ).data["sales"][0]
    other = create_workspace(name="Other synthetic scope", owner=owner)
    client.force_authenticate(owner)
    other_url = reverse("gold-list", args=[other.pk])
    assert client.get(other_url).data["purchases"] == []
    for name, record in [("gold-purchase", purchase), ("gold-sale", sale)]:
        target = reverse(name, args=[other.pk, record["id"]])
        assert client.delete(target).status_code == 404
        assert client.post(target, {}, format="json").status_code == 404
    assert (
        client.post(
            reverse("gold-sale-list", args=[other.pk]), sale_data(purchase), format="json"
        ).status_code
        == 404
    )
    assert client.get(url).data["summary"]["purchase_count"] == 1
