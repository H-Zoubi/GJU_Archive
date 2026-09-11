from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from common.models import TimeStampedModel

from .managers import UserManager


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    LECTURER = "lecturer", "Lecturer"
    MODERATOR = "moderator", "Moderator"
    ADMIN = "admin", "Admin"
    SUPERADMIN = "superadmin", "Super admin"


class User(AbstractBaseUser, PermissionsMixin):
    """
    Login identity. Email is the username and must be a GJU domain.

    Real permission gates come from Django Groups/Permissions (via
    PermissionsMixin); `role` is a convenience label for the common case.
    """

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)

    is_email_verified = models.BooleanField(default=False)
    is_gju_verified = models.BooleanField(
        default=False,
        help_text="Passed the GJU credential check at signup.",
    )
    is_banned = models.BooleanField(default=False)

    # How many of this user's uploads have been approved (drives auto-approve).
    approved_uploads_count = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    date_joined = models.DateTimeField(auto_now_add=True)

    # Set when this login belongs to a real GJU lecturer.
    instructor = models.OneToOneField(
        "academics.Instructor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    @property
    def is_trusted_uploader(self):
        return self.approved_uploads_count >= 5


class StudentProfile(TimeStampedModel):
    """Optional per-student academic info."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    major = models.ForeignKey(
        "academics.Major",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    entry_year = models.PositiveIntegerField(null=True, blank=True)
    expected_grad_year = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"Profile<{self.user.email}>"


class GjuCredential(TimeStampedModel):
    """
    Exists ONLY for students who opt into slide auto-import.

    Stores the Vault-transit ciphertext of the GJU password, never plaintext.
    Kept deliberately separate from User so it is trivial to keep off every
    serializer/admin/log and to delete on revoke. It must NEVER be exposed.
    """

    class SyncStatus(models.TextChoices):
        OK = "ok", "OK"
        AUTH_FAILED = "auth_failed", "Auth failed"
        ERROR = "error", "Error"
        NEVER = "never", "Never run"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="gju_credential",
    )
    # Opaque ciphertext produced by Vault transit; the app never holds the key.
    ciphertext = models.BinaryField()
    opted_in_at = models.DateTimeField(auto_now_add=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(
        max_length=20,
        choices=SyncStatus.choices,
        default=SyncStatus.NEVER,
    )

    class Meta:
        verbose_name = "GJU credential"

    def __str__(self):
        # Never include the ciphertext.
        return f"GjuCredential<{self.user_id}>"
