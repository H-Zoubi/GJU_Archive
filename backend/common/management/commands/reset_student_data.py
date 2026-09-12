"""
Wipe every student- and file-related row, leaving the academic catalog intact.

The database splits cleanly into two kinds of data:

* **Catalog / reference data** (the `academics` app: majors, subjects,
  courses, terms, offerings, schedules) -- seeded once (see `seed_academics`)
  and meant to persist across resets. It changes only when someone re-runs an
  import or edits it in the admin.
* **Everything else** -- accounts, uploaded/linked resources, votes,
  downloads, moderation reports/audit log, and importer bookkeeping. This is
  what a student or an upload creates, and it's what this command clears.

Use this to reset a demo/staging deployment to a clean slate without losing
the work that went into building the catalog. It is destructive and
irreversible -- it asks for confirmation unless --yes is passed.

    python manage.py reset_student_data                # prompts, keeps superusers
    python manage.py reset_student_data --yes
    python manage.py reset_student_data --yes --include-superusers
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from common import storage
from integrations.models import ImportRun, MoodleCourseMap
from moderation.models import AuditLog, Report, TakedownRequest
from resources.models import Download, Resource, Tag, Vote


class Command(BaseCommand):
    help = "Delete all student/file-related data; keep the academic catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Do not prompt for confirmation.",
        )
        parser.add_argument(
            "--include-superusers",
            action="store_true",
            help="Also delete superuser accounts (kept by default so admin access survives a reset).",
        )
        parser.add_argument(
            "--keep-files",
            action="store_true",
            help="Skip deleting the underlying objects from S3/MinIO; only clear database rows.",
        )

    def handle(self, *args, **options):
        User = get_user_model()

        user_qs = User.objects.all()
        if not options["include_superusers"]:
            user_qs = user_qs.exclude(is_superuser=True)

        counts = {
            "Users": user_qs.count(),
            "Resources": Resource.objects.count(),
            "Votes": Vote.objects.count(),
            "Downloads": Download.objects.count(),
            "Tags": Tag.objects.count(),
            "Reports": Report.objects.count(),
            "AuditLog entries": AuditLog.objects.count(),
            "TakedownRequests": TakedownRequest.objects.count(),
            "ImportRuns": ImportRun.objects.count(),
            "MoodleCourseMaps": MoodleCourseMap.objects.count(),
        }

        self.stdout.write("This will permanently delete:")
        for label, count in counts.items():
            self.stdout.write(f"  {label:20} {count}")
        if not options["include_superusers"]:
            self.stdout.write("  (superuser accounts are kept)")
        self.stdout.write(
            "The academic catalog (majors, courses, terms, offerings, ...) is not touched."
        )

        if not options["yes"]:
            answer = input("Type 'yes' to continue: ")
            if answer.strip().lower() != "yes":
                self.stdout.write("Aborted.")
                return

        file_keys = set(
            Resource.objects.exclude(file_key="").values_list("file_key", flat=True)
        )

        with transaction.atomic():
            # Moderation / audit / importer bookkeeping first -- it references
            # users and resources, which are deleted next.
            TakedownRequest.objects.all().delete()
            Report.objects.all().delete()
            AuditLog.objects.all().delete()
            ImportRun.objects.all().delete()
            MoodleCourseMap.objects.all().delete()

            # Vote/Download cascade from Resource and from User, but deleting
            # them explicitly keeps the count reported above accurate even if
            # a future model change loosens one of those FKs.
            Vote.objects.all().delete()
            Download.objects.all().delete()
            Resource.objects.all().delete()
            Tag.objects.all().delete()

            # user_qs.delete() returns the total row count across every model
            # it cascades into (StudentProfile, GjuCredential, ...), not just
            # User -- report the count we already took, not that number.
            deleted_users = counts["Users"]
            user_qs.delete()

        if not options["keep_files"] and file_keys:
            self.stdout.write(f"Deleting {len(file_keys)} object(s) from storage ...")
            failed = 0
            for key in file_keys:
                try:
                    storage.delete(key)
                except storage.StorageError as exc:
                    failed += 1
                    self.stderr.write(f"  could not delete {key}: {exc}")
            if failed:
                self.stdout.write(
                    self.style.WARNING(f"{failed} object(s) could not be deleted.")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Reset complete. Deleted {deleted_users} user(s).")
        )
