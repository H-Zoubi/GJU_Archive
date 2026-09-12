"""
Create (or rotate) a bot account for an importer job that runs as its own
process — the Telegram export importer today, the Moodle auto-import worker
later — and prints its API token once.

    python manage.py create_import_bot telegram
    python manage.py create_import_bot telegram --rotate

The token is what the job puts in its `Authorization: Token <key>` header
when calling the ingest API (see resources/views_ingest.py). It is not
stored anywhere but rest_framework's authtoken table and this command's
stdout — copy it into the job's own config now, because a plain re-run
without --rotate just prints the same key again, but there is nowhere else
in the app to look it up.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.authtoken.models import Token

User = get_user_model()


class Command(BaseCommand):
    help = "Create or rotate a service-account token for an importer job."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Short identifier, e.g. 'telegram'.")
        parser.add_argument(
            "--rotate", action="store_true",
            help="Invalidate the existing token and issue a new one.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        name = options["name"].strip().lower()
        if not name:
            raise CommandError("A name is required, e.g. 'telegram'.")
        email = f"{name}@bot.gjuarchive.local"

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "full_name": f"{name} importer",
                "is_service_account": True,
                "is_active": True,
            },
        )
        if not user.is_service_account:
            # Guard against colliding with a real account some other way.
            raise CommandError(f"{email} exists and is not a service account.")

        if options["rotate"]:
            Token.objects.filter(user=user).delete()
        token, _ = Token.objects.get_or_create(user=user)

        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Using existing'} bot account {email}"
        ))
        self.stdout.write(f"Token: {token.key}")
