"""Recorded sales of allotted IPO shares."""

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
