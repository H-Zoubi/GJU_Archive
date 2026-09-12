"""
Ensure the default GJU catalog (majors, subjects, courses, terms, offerings,
schedules) is present in the database.

The catalog is reference data, not something every deployment should have to
re-scrape from MyGJU and the study-plan PDFs on day one -- so a snapshot of it
is committed as a fixture (academics/fixtures/gju_catalog.json, built with
`manage.py dumpdata academics`) and this command loads it.

Idempotent by default: it only loads the fixture when the catalog is empty, so
a deployment that already has (possibly hand-corrected) catalog data is left
alone on every restart. Pass --force to reload the fixture regardless -- rows
it contains are upserted by primary key, but rows removed from a newer fixture
are not deleted.

    python manage.py seed_academics
    python manage.py seed_academics --force
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

from academics.models import Major

FIXTURE_NAME = "gju_catalog"


class Command(BaseCommand):
    help = "Load the default GJU catalog if it isn't already present."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reload the fixture even if the catalog is already populated.",
        )

    def handle(self, *args, **options):
        if Major.objects.exists() and not options["force"]:
            self.stdout.write(
                "Academics catalog already populated "
                f"({Major.objects.count()} majors) -- skipping seed."
            )
            return

        self.stdout.write(f"Loading {FIXTURE_NAME} fixture ...")
        call_command("loaddata", FIXTURE_NAME)

        # The fixture ships explicit primary keys. Postgres doesn't advance a
        # table's sequence just because a row with a given id was inserted, so
        # without this the next INSERT (e.g. from the admin, or a future
        # import_mygju run) would collide with a seeded row's id.
        if connection.vendor == "postgresql":
            out = StringIO()
            call_command("sqlsequencereset", "academics", stdout=out)
            sql = out.getvalue()
            if sql.strip():
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                self.stdout.write("Reset academics table sequences.")

        self.stdout.write(
            self.style.SUCCESS(f"Catalog ready: {Major.objects.count()} majors.")
        )
