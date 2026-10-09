import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class IPO(models.Model):
    class IssueType(models.TextChoices):
        MAINBOARD = "MAINBOARD", "Mainboard"
        SME = "SME", "SME"

    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        ALLOTMENT = "ALLOTMENT", "Allotment"
        LISTED = "LISTED", "Listed"
        CANCELLED = "CANCELLED", "Cancelled"

    class PublicationState(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issuer_name = models.CharField(max_length=200)
    symbol = models.CharField(max_length=40, blank=True)
    issue_type = models.CharField(max_length=9, choices=IssueType.choices)
    source_market = models.CharField(max_length=16, blank=True)
    listing_exchanges = models.CharField(max_length=7, blank=True)
    designated_exchange = models.CharField(max_length=3, blank=True)
    lower_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    upper_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    lot_size = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    open_date = models.DateField()
    close_date = models.DateField()
    allotment_date = models.DateField()
    listing_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.UPCOMING)
    publication_state = models.CharField(
        max_length=9, choices=PublicationState.choices, default=PublicationState.DRAFT
    )
    source_key = models.CharField(max_length=80)
    source_record_id = models.CharField(max_length=160)
    source_url = models.URLField(blank=True)
    source_observed_at = models.DateTimeField(default=timezone.now)
    source_payload_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_key", "source_record_id"], name="unique_ipo_source_record"
            )
        ]

    def __str__(self):
        return self.issuer_name

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.lower_price is not None and self.upper_price is not None:
            if self.lower_price > self.upper_price:
                errors["upper_price"] = "Upper price must be at least the lower price."
        if self.open_date and self.close_date and self.open_date > self.close_date:
            errors["close_date"] = "Closing date cannot be before opening date."
        if self.close_date and self.allotment_date and self.close_date > self.allotment_date:
            errors["allotment_date"] = "Allotment date cannot be before closing date."
        if self.allotment_date and self.listing_date and self.allotment_date > self.listing_date:
            errors["listing_date"] = "Listing date cannot be before allotment date."
        if errors:
            raise ValidationError(errors)


class IPOSourceLink(models.Model):
    """Explicit association between one feed identity and a canonical IPO."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ipo = models.ForeignKey(IPO, on_delete=models.PROTECT, related_name="source_links")
    source_key = models.CharField(max_length=80)
    source_record_id = models.CharField(max_length=160)
    canonical_enabled = models.BooleanField(default=False)
    rights_reference = models.CharField(max_length=250, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_key", "source_record_id"], name="unique_ipo_feed_identity"
            )
        ]

    def __str__(self):
        return f"{self.source_key}:{self.source_record_id}"


class IPOSourceSnapshot(models.Model):
    """Immutable normalized source observation; it does not publish or merge itself."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    link = models.ForeignKey(IPOSourceLink, on_delete=models.PROTECT, related_name="snapshots")
    payload = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    observed_at = models.DateTimeField()
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-observed_at", "-fetched_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["link", "payload_hash", "observed_at"],
                name="unique_ipo_feed_snapshot",
            )
        ]

    def __str__(self):
        return f"{self.link}: {self.observed_at}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("IPO source history cannot be changed")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("IPO source history cannot be deleted")

    def clean(self):
        if self.observed_at is not None and timezone.is_naive(self.observed_at):
            raise ValidationError({"observed_at": "Observation time must have a timezone."})


class IPOFeedBatch(models.Model):
    """One complete source response, including an empty current-issue list."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_key = models.CharField(max_length=20)
    source_url = models.URLField()
    payload_hash = models.CharField(max_length=64)
    row_keys = models.JSONField(blank=True)
    observed_at = models.DateTimeField()
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-observed_at", "-fetched_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_key", "payload_hash", "observed_at"],
                name="unique_ipo_feed_batch",
            )
        ]

    def __str__(self):
        return f"{self.source_key} batch at {self.observed_at}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("IPO feed batches cannot be changed")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("IPO feed batches cannot be deleted")


class IPOFeedObservation(models.Model):
    """Immutable exchange list row, even when planning facts are incomplete."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_key = models.CharField(max_length=20)
    source_record_id = models.CharField(max_length=160)
    source_url = models.URLField()
    raw_payload = models.JSONField()
    normalized_payload = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    observed_at = models.DateTimeField()
    fetched_at = models.DateTimeField(default=timezone.now)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    snapshot_created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-observed_at", "-fetched_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_key", "source_record_id", "payload_hash", "observed_at"],
                name="unique_ipo_feed_observation",
            )
        ]

    def __str__(self):
        return f"{self.source_key}:{self.source_record_id} at {self.observed_at}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("IPO feed observations cannot be changed")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("IPO feed observations cannot be deleted")

    def clean(self):
        if self.source_key not in {"nse", "bse"}:
            raise ValidationError({"source_key": "Unsupported exchange source"})
        if self.observed_at is not None and timezone.is_naive(self.observed_at):
            raise ValidationError({"observed_at": "Observation time must have a timezone."})


class IPOEnrichmentObservation(models.Model):
    """Immutable issue-detail or official-document extraction for a discovered symbol."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_key = models.CharField(max_length=20)
    stage = models.CharField(max_length=20)
    symbol = models.CharField(max_length=40)
    source_url = models.URLField(max_length=500)
    payload_hash = models.CharField(max_length=64)
    normalizer_version = models.PositiveSmallIntegerField(default=1)
    normalized_payload = models.JSONField(default=dict)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField()
    snapshot_created_at = models.DateTimeField(auto_now_add=True)
    outcome = models.CharField(max_length=20, default="OK")
    safe_error = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-fetched_at", "-snapshot_created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_key", "stage", "symbol", "payload_hash", "normalizer_version"],
                name="unique_ipo_enrichment_payload",
            )
        ]

    def __str__(self):
        return f"{self.source_key}:{self.stage}:{self.symbol}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("IPO enrichment observations cannot be changed")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("IPO enrichment observations cannot be deleted")

    def clean(self):
        if self.source_key not in {"nse", "bse", "sebi"}:
            raise ValidationError({"source_key": "Unsupported official source"})
        if self.stage not in {"DETAIL", "DOCUMENT"}:
            raise ValidationError({"stage": "Unsupported enrichment stage"})
        if self.outcome not in {"OK", "ERROR"}:
            raise ValidationError({"outcome": "Unsupported enrichment outcome"})
        if self.source_updated_at and timezone.is_naive(self.source_updated_at):
            raise ValidationError({"source_updated_at": "Timezone is required"})
        if self.fetched_at and timezone.is_naive(self.fetched_at):
            raise ValidationError({"fetched_at": "Timezone is required"})


class SEBIFiling(models.Model):
    """Official filing metadata awaiting deterministic fact extraction or review."""

    source_url = models.URLField(unique=True)
    issuer_name = models.CharField(max_length=200)
    document_type = models.CharField(max_length=40)
    document_url = models.URLField(blank=True)
    filing_date = models.DateField()
    fetched_at = models.DateTimeField(default=timezone.now)
    review_state = models.CharField(max_length=20, default="REVIEW_REQUIRED")

    class Meta:
        ordering = ["-filing_date", "issuer_name"]

    def __str__(self):
        return f"{self.issuer_name}: {self.document_type}"


class IPOProviderSyncState(models.Model):
    """Persistent, safe operational status for an official IPO source."""

    source_key = models.CharField(max_length=40, unique=True)
    enabled = models.BooleanField(default=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    fetched_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    last_status = models.CharField(max_length=40, blank=True)
    last_safe_error = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return self.source_key


class IPOContentVersion(models.Model):
    class ContentType(models.TextChoices):
        COMPANY = "COMPANY", "Company summary"
        FINANCIAL = "FINANCIAL", "Financial summary"
        RISK = "RISK", "Risk summary"

    class ReviewState(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        REVIEWED = "REVIEWED", "Reviewed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ipo = models.ForeignKey(IPO, on_delete=models.CASCADE, related_name="content_versions")
    content_type = models.CharField(max_length=10, choices=ContentType.choices)
    source_document_id = models.CharField(max_length=160)
    source_document_url = models.URLField(blank=True)
    source_payload_hash = models.CharField(max_length=64, blank=True)
    provider_key = models.CharField(max_length=80)
    model_name = models.CharField(max_length=120, blank=True)
    prompt_version = models.CharField(max_length=80, blank=True)
    draft_text = models.TextField()
    review_state = models.CharField(
        max_length=8, choices=ReviewState.choices, default=ReviewState.DRAFT
    )
    generated_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ipo_content_versions_reviewed",
    )

    class Meta:
        ordering = ["-generated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["ipo", "content_type", "source_document_id", "provider_key", "model_name"],
                name="unique_ipo_content_document_version",
            )
        ]

    def __str__(self):
        return f"{self.ipo.issuer_name}: {self.content_type}"


class IPOContentRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_version = models.ForeignKey(
        IPOContentVersion, on_delete=models.CASCADE, related_name="revisions"
    )
    text = models.TextField()
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ipo_content_revisions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.content_version}: {self.created_at}"


class IPOFieldOverride(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ipo = models.ForeignKey(IPO, on_delete=models.CASCADE, related_name="field_overrides")
    field_name = models.CharField(max_length=32)
    value = models.TextField()
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ipo_overrides_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resumed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ipo_overrides_resumed",
    )
    resumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["ipo", "field_name"],
                condition=Q(resumed_at__isnull=True),
                name="unique_active_ipo_field_override",
            )
        ]

    def __str__(self):
        return f"{self.ipo.issuer_name}: {self.field_name}"


class GMPObservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ipo = models.ForeignKey(IPO, on_delete=models.PROTECT, related_name="gmp_observations")
    source_key = models.CharField(max_length=80)
    value_per_share = models.DecimalField(max_digits=10, decimal_places=2)
    observed_at = models.DateTimeField()
    fetched_at = models.DateTimeField(default=timezone.now)
    source_url = models.URLField(blank=True)
    source_record_id = models.CharField(max_length=160, blank=True)
    source_payload_hash = models.CharField(max_length=64, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["-observed_at", "-fetched_at", "-id"]

    def __str__(self):
        return f"{self.ipo.issuer_name}: {self.value_per_share} ({self.source_key})"

    def save(self, *args, **kwargs):
        if self._state.adding is False:
            raise ValueError("GMP history cannot be changed")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("GMP history cannot be deleted")

    def clean(self):
        if self.observed_at is not None and timezone.is_naive(self.observed_at):
            raise ValidationError({"observed_at": "Observation time must have a timezone."})


class GMPObservationOverride(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    observation = models.ForeignKey(
        GMPObservation, on_delete=models.CASCADE, related_name="overrides"
    )
    value_per_share = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=500)
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="gmp_observation_overrides"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resumed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="gmp_observation_overrides_resumed",
    )
    resumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["observation"],
                condition=Q(resumed_at__isnull=True),
                name="unique_active_gmp_observation_override",
            )
        ]

    def __str__(self):
        return f"{self.observation}: {self.value_per_share}"


class GMPProviderState(models.Model):
    provider_key = models.CharField(max_length=80, unique=True)
    enabled = models.BooleanField(default=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_type = models.CharField(max_length=120, blank=True)
    override_value_per_share = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    override_expires_at = models.DateTimeField(null=True, blank=True)
    override_reason = models.CharField(max_length=500, blank=True)
    override_set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="gmp_provider_overrides",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider_key"]

    def __str__(self):
        return self.provider_key

    def clean(self):
        if self.override_value_per_share is None:
            if self.override_expires_at is not None or self.override_reason:
                raise ValidationError("An override value is required for expiry and reason.")
        elif self.override_expires_at is None or not self.override_reason.strip():
            raise ValidationError("An override requires expiry and reason.")


class GMPPolicy(models.Model):
    """Founder-editable beta thresholds for current GMP and source exceptions."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    freshness_hours = models.PositiveIntegerField(default=24, validators=[MinValueValidator(1)])
    conflict_threshold_percent_points = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )

    def __str__(self):
        return "GMP consensus policy"

    def clean(self):
        if self.pk != 1:
            raise ValidationError("Only one GMP policy can be active.")


class IPOUserDecision(models.Model):
    class Decision(models.TextChoices):
        DEFAULT = "DEFAULT", "Automatic"
        APPLY = "APPLY", "Apply"
        SKIP = "SKIP", "Skip"

    class Mode(models.TextChoices):
        RETAIL_ONLY = "RETAIL_ONLY", "Retail Only"
        RETAIL_PLUS_SHNI = "RETAIL_PLUS_SHNI", "Retail + sHNI"
        SHNI_PREFERRED = "SHNI_PREFERRED", "sHNI Preferred"
        CUSTOM = "CUSTOM", "Custom"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.CASCADE, related_name="ipo_decisions"
    )
    ipo = models.ForeignKey(IPO, on_delete=models.CASCADE, related_name="workspace_decisions")
    decision = models.CharField(max_length=7, choices=Decision.choices, default=Decision.DEFAULT)
    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.RETAIL_ONLY)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "ipo"], name="unique_workspace_ipo_decision"
            )
        ]

    def __str__(self):
        return f"{self.workspace.name}: {self.ipo.issuer_name} {self.decision}"
