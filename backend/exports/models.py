"""Private file references and their exact source plan versions."""

import uuid

from django.conf import settings
from django.db import models


class PlanExport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan_run = models.ForeignKey(
        "planner.PlanRun", on_delete=models.PROTECT, related_name="exports"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    format_id = models.CharField(max_length=40)
    format_version = models.CharField(max_length=40)
    content_type = models.CharField(max_length=100)
    object_key = models.CharField(max_length=240, unique=True)
    content_sha256 = models.CharField(max_length=64)
    planner_version = models.CharField(max_length=40)
    settings_version = models.CharField(max_length=80)
    input_snapshot_hash = models.CharField(max_length=64)
    plan_output_hash = models.CharField(max_length=64)
    row_count = models.PositiveIntegerField()
    planned_total = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.format_id} export for plan {self.plan_run_id}"
