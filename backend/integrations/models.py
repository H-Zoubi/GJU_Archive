from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class ImportRun(TimeStampedModel):
    """One execution of the weekly Moodle importer for one user."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial"
        AUTH_FAILED = "auth_failed", "Auth failed"
        ERROR = "error", "Error"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="import_runs"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUCCESS)
    courses_seen = models.PositiveIntegerField(default=0)
    files_added = models.PositiveIntegerField(default=0)
    files_skipped = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"ImportRun<{self.user_id} {self.status}>"


class MoodleCourseMap(TimeStampedModel):
    """Learned mapping from a Moodle course to our catalog."""

    class Confidence(models.TextChoices):
        AUTO = "auto", "Auto-matched"
        CONFIRMED = "confirmed", "Confirmed"

    moodle_course_id = models.PositiveIntegerField(unique=True)
    offering = models.ForeignKey(
        "academics.CourseOffering",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moodle_maps",
    )
    course = models.ForeignKey(
        "academics.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moodle_maps",
    )
    moodle_shortname = models.CharField(max_length=255, blank=True)
    moodle_fullname = models.CharField(max_length=255, blank=True)
    confidence = models.CharField(
        max_length=10, choices=Confidence.choices, default=Confidence.AUTO
    )

    def __str__(self):
        return f"MoodleCourseMap<{self.moodle_course_id}>"
