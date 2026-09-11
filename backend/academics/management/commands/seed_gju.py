"""
Seed the catalog with real GJU majors and recent terms.

Data was extracted from the public program pages on gju.edu.jo (the eight
schools' Undergraduate/Graduate Programs pages) in September 2026. Schools and
departments are intentionally not modeled; only the degree programs (majors)
are stored. Tracks/specializations are omitted by design.

Idempotent: safe to run repeatedly (upserts on Major.code / Term).

    python manage.py seed_gju
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from academics.models import DegreeLevel, Major, Term

B = DegreeLevel.BACHELOR

# Scope is bachelor programs only for now. (code, name, partner_institution)
MAJORS = [
    # --- School of Computing (SC) ---
    ("CS", "Computer Science", ""),
    ("CE", "Computer Engineering", ""),
    ("GDMI", "Game Design and Media Informatics", ""),  # joint SC + SABE
    # --- Business School (BS) ---
    ("IA", "International Accounting", ""),
    ("LS", "Logistics Sciences", ""),
    ("MGTS", "Management Sciences", ""),
    ("BIDA", "Business Intelligence and Data Analytics", ""),
    ("DMKT", "Digital Marketing", ""),
    # --- School of Applied Humanities and Social Sciences (SAHSS) ---
    ("TRANS", "Translation (German, English, Arabic)", ""),
    ("GEBC", "German and English for Business and Communication", ""),
    # --- School of Applied Medical Sciences (SAMS) ---
    ("BME", "Biomedical Engineering", ""),
    ("PCE", "Pharmaceutical and Chemical Engineering", ""),
    # --- School of Applied Technical Sciences (SATS) ---
    ("IE", "Industrial Engineering", ""),
    ("MME", "Mechanical and Maintenance Engineering", ""),
    ("MTE", "Mechatronics Engineering", ""),
    # --- School of Architecture and Built Environment (SABE) ---
    ("ARCH", "Architecture", ""),
    ("INAR", "Interior Architecture", ""),
    ("DVC", "Design and Visual Communication", ""),
    # --- School of Sustainable Systems Engineering (SSSE) ---
    ("SISE", "Sustainable Infrastructure Systems Engineering", ""),
    ("EE", "Electrical Engineering", ""),
    ("ENE", "Energy Engineering", ""),
    # --- School of Nursing (SN) ---
    ("NUR", "Nursing", ""),
]

# Recent terms. Current term flagged for the 2026/2027 academic year.
TERMS = [
    (Term.Season.FIRST, 2025, False),
    (Term.Season.SECOND, 2025, False),
    (Term.Season.SUMMER, 2025, False),
    (Term.Season.FIRST, 2026, True),
    (Term.Season.SECOND, 2026, False),
    (Term.Season.SUMMER, 2026, False),
]


class Command(BaseCommand):
    help = "Seed the catalog with real GJU majors and recent terms."

    @transaction.atomic
    def handle(self, *args, **options):
        # Scope is bachelor-only: drop any previously seeded non-bachelor majors.
        removed = Major.objects.exclude(degree_level=B).delete()[0]

        created_m = updated_m = 0
        for code, name, partner in MAJORS:
            _, created = Major.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "degree_level": B,
                    "partner_institution": partner,
                    "is_active": True,
                },
            )
            created_m += int(created)
            updated_m += int(not created)
        if removed:
            self.stdout.write(f"Removed {removed} non-bachelor majors (out of scope).")

        created_t = 0
        for season, year, is_current in TERMS:
            _, created = Term.objects.update_or_create(
                season=season, year=year, defaults={"is_current": is_current}
            )
            created_t += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Majors: {created_m} created, {updated_m} updated "
                f"({Major.objects.count()} total). "
                f"Terms: {created_t} created ({Term.objects.count()} total)."
            )
        )
