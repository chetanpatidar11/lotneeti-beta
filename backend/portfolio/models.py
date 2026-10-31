"""IPO share sales and separate physical-gold purchase/sale records."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Sale(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.Application", on_delete=models.PROTECT, related_name="sales"
    )
    quantity = models.PositiveIntegerField()
    price_per_share = models.DecimalField(max_digits=12, decimal_places=2)
    sold_on = models.DateField()
    charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey("accounts.User", on_delete=models.PROTECT)

    class Meta:
        ordering = ["-sold_on", "-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sale_positive_quantity"),
            models.CheckConstraint(condition=Q(price_per_share__gt=0), name="sale_positive_price"),
            models.CheckConstraint(condition=Q(charges__gte=0), name="sale_nonnegative_charges"),
        ]

    def __str__(self):
        return f"{self.quantity} shares sold for {self.application_id}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        if self.application_id and self.application.status != "ALLOTTED":
            raise ValidationError("Sales require an allotted application")


class GoldPurchase(models.Model):
    """One physical-gold purchase lot, independent of IPO bank commitments."""

    class Form(models.TextChoices):
        COIN = "COIN", "Coin"
        BAR = "BAR", "Bar"
        JEWELLERY = "JEWELLERY", "Jewellery"
        OTHER = "OTHER", "Other physical gold"

    class PriceMode(models.TextChoices):
        LIVE = "LIVE", "Live market price"
        MANUAL = "MANUAL", "My resale quote"

    price_mode = models.CharField(max_length=6, choices=PriceMode.choices, default=PriceMode.LIVE)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.PROTECT, related_name="gold_purchases"
    )
    request_id = models.UUIDField()
    name = models.CharField(max_length=120)
    form = models.CharField(max_length=12, choices=Form.choices)
    owner_name = models.CharField(max_length=120, blank=True)
    purity = models.CharField(max_length=20)
    purchased_on = models.DateField()
    grams = models.DecimalField(max_digits=14, decimal_places=6)
    total_cost = models.DecimalField(max_digits=16, decimal_places=2)
    current_price_per_gram = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    price_updated_at = models.DateTimeField(null=True, blank=True)
    seller = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)

    class Meta:
        ordering = ["-purchased_on", "-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "request_id"], name="unique_gold_purchase_request"
            ),
            models.CheckConstraint(condition=Q(grams__gt=0), name="gold_purchase_positive_grams"),
            models.CheckConstraint(
                condition=Q(total_cost__gt=0), name="gold_purchase_positive_cost"
            ),
            models.CheckConstraint(
                condition=Q(current_price_per_gram__isnull=True) | Q(current_price_per_gram__gt=0),
                name="gold_purchase_positive_quote",
            ),
        ]

    def __str__(self):
        return f"Physical gold purchase {self.pk}"


class GoldSale(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase = models.ForeignKey(GoldPurchase, on_delete=models.PROTECT, related_name="gold_sales")
    request_id = models.UUIDField()
    sold_on = models.DateField()
    grams = models.DecimalField(max_digits=14, decimal_places=6)
    net_proceeds = models.DecimalField(max_digits=16, decimal_places=2)
    notes = models.CharField(max_length=500, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)

    class Meta:
        ordering = ["sold_on", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase", "request_id"], name="unique_gold_sale_request"
            ),
            models.CheckConstraint(condition=Q(grams__gt=0), name="gold_sale_positive_grams"),
            models.CheckConstraint(
                condition=Q(net_proceeds__gt=0), name="gold_sale_positive_proceeds"
            ),
        ]

    def __str__(self):
        return f"Physical gold sale {self.pk}"
