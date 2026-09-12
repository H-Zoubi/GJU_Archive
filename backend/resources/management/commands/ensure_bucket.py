"""Create the object-storage bucket if it does not exist yet."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from common import storage


class Command(BaseCommand):
    help = "Create the configured S3/MinIO bucket if it is missing."

    def handle(self, *args, **options):
        try:
            created = storage.ensure_bucket()
        except storage.StorageError as exc:
            raise CommandError(
                f"Could not reach {settings.S3_ENDPOINT_URL}: {exc}"
            ) from exc
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created bucket {settings.S3_BUCKET}."))
        else:
            self.stdout.write(f"Bucket {settings.S3_BUCKET} already exists.")
