from django.conf import settings
from django.db import models
from django.utils.text import slugify

from common.models import SoftDeleteModel, TimeStampedModel


class ResourceType(models.TextChoices):
    PAST_PAPER = "past_paper", "Past paper"
    MIDTERM = "midterm", "Midterm"
    FINAL = "final", "Final"
    QUIZ = "quiz", "Quiz"
    ASSIGNMENT = "assignment", "Assignment"
    SOLUTION = "solution", "Solution"
    SLIDES = "slides", "Slides"
    LECTURE_NOTES = "lecture_notes", "Lecture notes"
    SUMMARY = "summary", "Summary"
    LAB = "lab", "Lab"
    PROJECT = "project", "Project"
    BOOK = "book", "Book"
    VIDEO = "video", "Video"
    OTHER = "other", "Other"


class Tag(TimeStampedModel):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:50]
        super().save(*args, **kwargs)


class Resource(TimeStampedModel, SoftDeleteModel):
    class Kind(models.TextChoices):
        FILE = "file", "File"
        LINK = "link", "Link"

    class Source(models.TextChoices):
        UPLOAD = "upload", "Upload"
        TELEGRAM_IMPORT = "telegram_import", "Telegram import"
        AUTO_IMPORT = "auto_import", "Auto import"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        REMOVED = "removed", "Removed"

    class Visibility(models.TextChoices):
        PUBLIC_META = "public_meta", "Public metadata, gated download"
        GJU_ONLY = "gju_only", "GJU only"

    course = models.ForeignKey(
        "academics.Course", on_delete=models.CASCADE, related_name="resources"
    )
    offering = models.ForeignKey(
        "academics.CourseOffering",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resources",
    )
    term = models.ForeignKey(
        "academics.Term",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resources",
    )
    instructor = models.ForeignKey(
        "academics.Instructor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resources",
    )

    type = models.CharField(max_length=20, choices=ResourceType.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, related_name="resources", blank=True)

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.FILE)

    # File fields (kind == FILE)
    file_key = models.CharField(max_length=512, blank=True, help_text="Object key in MinIO/S3")
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=120, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    # Set once the browser's direct PUT has been confirmed against the bucket.
    # A file row with this null is a started-but-abandoned upload; nothing is
    # ever served from one, and `purge_incomplete_uploads` sweeps them.
    upload_completed_at = models.DateTimeField(null=True, blank=True)

    # Link fields (kind == LINK)
    url = models.URLField(max_length=1000, blank=True)

    class LinkStatus(models.TextChoices):
        OK = "ok", "OK"
        BROKEN = "broken", "Broken"
        UNCHECKED = "unchecked", "Unchecked"

    link_status = models.CharField(
        max_length=10, choices=LinkStatus.choices, default=LinkStatus.UNCHECKED
    )

    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploads",
    )
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.UPLOAD)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    visibility = models.CharField(
        max_length=15, choices=Visibility.choices, default=Visibility.PUBLIC_META
    )

    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_resources",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["course", "type", "status"]),
        ]
        constraints = [
            # Dedup identical files within a course (ignoring blank hashes).
            models.UniqueConstraint(
                fields=["course", "sha256"],
                condition=models.Q(kind="file") & ~models.Q(sha256=""),
                name="uniq_course_file_sha256",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_type_display()})"


class Download(TimeStampedModel):
    """
    One row per file handed out.

    Kept because it is the only thing that can answer "how many downloads has
    this student used this month" — which is what a quota-shaped paywall needs,
    and which cannot be reconstructed after the fact if we did not log it. It
    also tells moderators which files are actually worth keeping.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="downloads",
    )
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="downloads")

    class Meta:
        indexes = [
            # Serves both "this user's recent downloads" (quota) and ordering.
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["resource", "-created_at"]),
        ]

    def __str__(self):
        return f"Download<{self.user_id}->{self.resource_id}>"


class Vote(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="votes"
    )
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="votes")
    value = models.SmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "resource"], name="uniq_user_vote")
        ]

    def __str__(self):
        return f"Vote<{self.user_id}->{self.resource_id}={self.value}>"
