"""
Weekly-ish sync worker: for each opted-in student, decrypts their GJU
password via Vault transit, logs into MyGJU, and refreshes their
StudentProfile (major, entry year) from the profile page.

Deliberately the only process meant to ever hold VAULT_DECRYPT_TOKEN -- run
this as its own deployment, separate from the public web app (see
accounts/vault_transit.py and the gju-vault-password-storage-decision memo).
Not wired into docker-compose or any scheduler yet; run it manually:

    python manage.py gju_sync_worker [--email one@gju.edu.jo]
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from ... import gju_verifier, services, vault_transit
from ...models import GjuCredential

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Refresh each opted-in student's profile (major, entry year) from MyGJU."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Sync only this one student (for testing).")

    def handle(self, *args, **options):
        credentials = GjuCredential.objects.select_related("user")
        if options["email"]:
            credentials = credentials.filter(user__email=options["email"])

        if not credentials.exists():
            self.stdout.write(self.style.WARNING("No matching opted-in students."))
            return

        for credential in credentials:
            self._sync_one(credential)

    def _sync_one(self, credential: GjuCredential) -> None:
        user = credential.user
        try:
            password = vault_transit.decrypt(credential.ciphertext.decode("ascii"))
        except Exception:
            logger.exception("Could not decrypt credential for %s", user.email)
            self._mark(credential, GjuCredential.SyncStatus.ERROR)
            return

        try:
            profile = services.refresh_profile_from_mygju(user, password)
        except gju_verifier.GjuSessionError as exc:
            logger.warning("MyGJU login failed syncing %s: %s", user.email, exc)
            self._mark(credential, GjuCredential.SyncStatus.AUTH_FAILED)
            return
        except Exception:
            logger.exception("Unexpected error syncing %s", user.email)
            self._mark(credential, GjuCredential.SyncStatus.ERROR)
            return

        self._mark(credential, GjuCredential.SyncStatus.OK)
        self.stdout.write(self.style.SUCCESS(
            f"Synced {user.email}: major={profile.major}, entry_year={profile.entry_year}"
        ))

    def _mark(self, credential: GjuCredential, status: str) -> None:
        credential.last_sync_status = status
        credential.last_sync_at = timezone.now()
        credential.save(update_fields=["last_sync_status", "last_sync_at"])
