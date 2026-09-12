"""
Nightly storage cleanup.

Two kinds of dead weight accumulate:

* **Abandoned uploads** -- a row was reserved and a presigned URL handed out,
  then the student closed the tab. The row is unusable (nothing is served
  while `upload_completed_at` is null) and may or may not have an object
  behind it.
* **Removed resources** -- soft-deleted by a moderator. They are kept for a
  grace period so a mistaken removal can be undone, then the bytes go.

Object keys are content-addressed, so two resources in different courses can
legitimately share one object. An object is only deleted once no live resource
still points at that key.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from common import storage
from resources.models import Resource


class Command(BaseCommand):
    help = "Delete abandoned uploads and purge the files of long-removed resources."

    def add_arguments(self, parser):
        parser.add_argument(
            "--abandoned-hours",
            type=int,
            default=24,
            help="Age after which an incomplete upload is abandoned (default: 24).",
        )
        parser.add_argument(
            "--grace-days",
            type=int,
            default=30,
            help="Days a removed resource is kept before its file is deleted (default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without touching anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()

        abandoned = Resource.objects.filter(
            kind=Resource.Kind.FILE,
            upload_completed_at__isnull=True,
            created_at__lt=now - timedelta(hours=options["abandoned_hours"]),
        )
        self._purge(abandoned, "abandoned upload", dry_run, delete_row=True)

        removed = Resource.objects.filter(
            kind=Resource.Kind.FILE,
            status=Resource.Status.REMOVED,
            deleted_at__lt=now - timedelta(days=options["grace_days"]),
        ).exclude(file_key="")
        self._purge(removed, "removed resource", dry_run, delete_row=False)

    def _purge(self, queryset, label, dry_run, *, delete_row):
        count = 0
        for resource in queryset:
            key = resource.file_key
            if key and not self._key_still_in_use(key, resource.pk):
                if dry_run:
                    self.stdout.write(f"would delete object {key} ({label})")
                else:
                    try:
                        storage.delete(key)
                    except storage.StorageError as exc:
                        self.stderr.write(f"could not delete {key}: {exc}")
                        continue
            if not dry_run:
                if delete_row:
                    resource.delete()
                else:
                    # Keep the row as a tombstone so the removal stays visible
                    # to moderators; only the bytes and the key go.
                    resource.file_key = ""
                    resource.save(update_fields=["file_key"])
            count += 1
        verb = "would purge" if dry_run else "purged"
        self.stdout.write(self.style.SUCCESS(f"{verb} {count} {label}(s)."))

    @staticmethod
    def _key_still_in_use(key: str, excluding_pk: int) -> bool:
        """Another live resource sharing this content-addressed object."""
        return (
            Resource.objects.filter(file_key=key)
            .exclude(pk=excluding_pk)
            .exclude(status=Resource.Status.REMOVED)
            .exists()
        )
