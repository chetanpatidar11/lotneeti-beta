from django.conf import settings
from django.db import models
from django.db.models import Q


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    workspace = models.ForeignKey(
        "accounts.Workspace", null=True, blank=True, on_delete=models.SET_NULL
    )
    object_type = models.CharField(max_length=120)
    object_id = models.CharField(max_length=64)
    action = models.CharField(max_length=100)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.action} ({self.object_type}:{self.object_id})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Audit events cannot be changed")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit events cannot be deleted")


class BetaEvent(models.Model):
    class Type(models.TextChoices):
        ACTIVATED = "ACTIVATED"
        PLAN_GENERATED = "PLAN_GENERATED"
        PLAN_EDITED = "PLAN_EDITED"
        EXPORT_GENERATED = "EXPORT_GENERATED"
        ALLOTMENT_RECORDED = "ALLOTMENT_RECORDED"
        PNL_COMPLETED = "PNL_COMPLETED"

    workspace = models.ForeignKey("accounts.Workspace", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=32, choices=Type.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["event_type", "created_at"])]

    def __str__(self):
        return self.event_type


class FeatureFlag(models.Model):
    """A platform default with an optional workspace-specific override."""

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=100)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="feature_flags",
    )
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key"],
                condition=Q(workspace__isnull=True),
                name="unique_platform_feature_flag",
            ),
            models.UniqueConstraint(
                fields=["key", "workspace"],
                condition=Q(workspace__isnull=False),
                name="unique_workspace_feature_flag",
            ),
        ]

    def __str__(self):
        scope = "platform" if self.workspace_id is None else str(self.workspace_id)
        return f"{scope}:{self.key}={self.enabled}"
