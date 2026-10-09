"""Workspace-scoped snapshots and rows for explainable planner runs."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PlanRun(models.Model):
    class Status(models.TextChoices):
        READY = "READY", "Ready"
        BLOCKED = "BLOCKED", "Blocked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.CASCADE, related_name="plan_runs"
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="plan_runs"
    )
    planner_version = models.CharField(max_length=40)
    settings_version = models.CharField(max_length=80)
    input_snapshot_hash = models.CharField(max_length=64)
    output_hash = models.CharField(max_length=64)
    input_snapshot = models.TextField()
    status = models.CharField(max_length=7, choices=Status.choices)
    planned_total = models.DecimalField(max_digits=14, decimal_places=2)
    audit_issues = models.JSONField(default=list)
    uncovered = models.JSONField(default=list)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at", "-id"]

    def __str__(self):
        return f"Plan {self.pk} for workspace {self.workspace_id}"


class PlannerPolicy(models.Model):
    class Scope(models.TextChoices):
        GLOBAL = "GLOBAL", "Global default"
        BANK = "BANK", "Bank override"

    class Policy(models.TextChoices):
        ALLOW = "ALLOW", "Allow"
        WARN = "WARN", "Warn"
        DISALLOW = "DISALLOW", "Disallow"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=6, choices=Scope.choices)
    bank = models.ForeignKey(
        "funding.BankAccount",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="planner_policies",
    )
    policy = models.CharField(max_length=8, choices=Policy.choices)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_until = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="planner_policies_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-created_at", "-id"]

    def __str__(self):
        target = self.bank_id or "platform"
        return f"{target}: {self.policy}"

    def clean(self):
        if self.scope == self.Scope.GLOBAL and self.bank_id is not None:
            raise ValidationError("Global policies cannot target a bank")
        if self.scope == self.Scope.BANK and self.bank_id is None:
            raise ValidationError("Bank policies require a bank")
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValidationError("Policy end must be after its start")
        if not self.reason.strip():
            raise ValidationError("A policy reason is required")


class PlanRow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan_run = models.ForeignKey(PlanRun, on_delete=models.CASCADE, related_name="rows")
    position = models.PositiveIntegerField()
    ipo_ref = models.CharField(max_length=80)
    applicant_ref = models.CharField(max_length=80)
    category = models.CharField(max_length=8)
    lots = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    demat_ref = models.CharField(max_length=80)
    bank_ref = models.CharField(max_length=80)
    upi_ref = models.CharField(max_length=80)
    locked = models.BooleanField(default=False)
    warnings = models.JSONField(default=list)
    blocking_reasons = models.JSONField(default=list)
    reasons = models.JSONField(default=list)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan_run", "position"], name="unique_plan_row_position"
            )
        ]

    def __str__(self):
        return f"Plan row {self.position} for {self.plan_run_id}"
