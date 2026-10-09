"""A submitted IPO application keeps the exact reviewed mapping."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Application(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        SUBMITTED = "SUBMITTED", "Submitted"
        BLOCKED = "BLOCKED", "Blocked"
        ALLOTTED = "ALLOTTED", "Allotted"
        NOT_ALLOTTED = "NOT_ALLOTTED", "Not allotted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.PROTECT, related_name="applications"
    )
    plan_row = models.OneToOneField(
        "planner.PlanRow", on_delete=models.PROTECT, related_name="application"
    )
    ipo = models.ForeignKey("ipos.IPO", on_delete=models.PROTECT, related_name="applications")
    applicant = models.ForeignKey(
        "investors.Investor", on_delete=models.PROTECT, related_name="applications"
    )
    demat = models.ForeignKey(
        "investors.DematAccount", on_delete=models.PROTECT, related_name="applications"
    )
    bank = models.ForeignKey(
        "funding.BankAccount", on_delete=models.PROTECT, related_name="applications"
    )
    upi = models.ForeignKey(
        "funding.UPIHandle", on_delete=models.PROTECT, related_name="applications"
    )
    category = models.CharField(max_length=8)
    lots = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    planned_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True)
    result_at = models.DateTimeField(null=True, blank=True)
    expected_release_date = models.DateField(null=True, blank=True)
    allotted_quantity = models.PositiveIntegerField(null=True, blank=True)
    actual_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    shares_credited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-planned_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "ipo", "applicant"], name="unique_workspace_ipo_applicant"
            )
        ]

    def __str__(self):
        return f"{self.applicant_id} application for {self.ipo_id}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        if not all(
            (
                self.workspace_id,
                self.plan_row_id,
                self.ipo_id,
                self.applicant_id,
                self.demat_id,
                self.bank_id,
                self.upi_id,
            )
        ):
            return
        row = self.plan_row
        if (
            row.plan_run.workspace_id != self.workspace_id
            or str(self.ipo_id) != row.ipo_ref
            or str(self.applicant_id) != row.applicant_ref
            or str(self.demat_id) != row.demat_ref
            or str(self.bank_id) != row.bank_ref
            or str(self.upi_id) != row.upi_ref
            or self.category != row.category
            or self.lots != row.lots
            or self.amount != row.amount
        ):
            raise ValidationError("Application mapping must match its reviewed plan row")
        if (
            self.applicant.workspace_id != self.workspace_id
            or self.bank.workspace_id != self.workspace_id
            or self.demat.investor_id != self.applicant_id
            or self.upi.bank_id != self.bank_id
        ):
            raise ValidationError("Application mapping is outside its workspace")
