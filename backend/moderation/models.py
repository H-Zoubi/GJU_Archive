from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Report(TimeStampedModel):
    class Reason(models.TextChoices):
        BROKEN_LINK = "broken_link", "Broken link"
        WRONG_COURSE = "wrong_course", "Wrong course"
        DUPLICATE = "duplicate", "Duplicate"
        LOW_QUALITY = "low_quality", "Low quality"
        INAPPROPRIATE = "inappropriate", "Inappropriate"
        COPYRIGHT = "copyright", "Copyright / takedown"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    resource = models.ForeignKey(
        "resources.Resource", on_delete=models.CASCADE, related_name="reports"
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    note = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handled_reports",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report<{self.get_reason_display()} on {self.resource_id}>"


class AuditLog(TimeStampedModel):
    """Append-only record of who did what. Never edited."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
        help_text="Null for system / importer actions.",
    )
    action = models.CharField(max_length=100, help_text="e.g. resource.approve, user.ban")
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.actor_id or 'system'}"


class TakedownRequest(TimeStampedModel):
    """Formal copyright / removal request (future)."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACTIONED = "actioned", "Actioned"
        REJECTED = "rejected", "Rejected"

    resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="takedowns",
    )
    requester_email = models.EmailField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    def __str__(self):
        return f"Takedown<{self.requester_email}>"
