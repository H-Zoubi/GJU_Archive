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
M = DegreeLevel.MASTER
P = DegreeLevel.PHD
D = DegreeLevel.DIPLOMA

# (code, name, degree_level, partner_institution)
MAJORS = [
    # --- School of Computing (SC) ---
    ("CS", "Computer Science", B, ""),
    ("CE", "Computer Engineering", B, ""),
    ("GDMI", "Game Design and Media Informatics", B, ""),  # joint SC + SABE
    ("MCE", "Computer Engineering", M, ""),
    ("ESE", "Enterprise Systems Engineering", M, "PSUT"),
    # --- Business School (BS) ---
    ("IA", "International Accounting", B, ""),
    ("LS", "Logistics Sciences", B, ""),
    ("MGTS", "Management Sciences", B, ""),
    ("BIDA", "Business Intelligence and Data Analytics", B, ""),
    ("DMKT", "Digital Marketing", B, ""),
    ("MLM", "Logistics Management", M, ""),
    ("MBA", "Business Administration (MBA)", M, ""),
    ("HDTAX", "Taxation", D, ""),
    # --- School of Applied Humanities and Social Sciences (SAHSS) ---
    ("TRANS", "Translation (German, English, Arabic)", B, ""),
    ("GEBC", "German and English for Business and Communication", B, ""),
    ("GFL", "German as a Foreign Language", M, ""),
    ("GFLPHD", "German as a Foreign Language", P, ""),
    ("MASW", "Social Work", M, ""),
    ("SWPHD", "Social Work", P, ""),
    ("HDIE", "Integrated Education", D, ""),
    # --- School of Applied Medical Sciences (SAMS) ---
    ("BME", "Biomedical Engineering", B, ""),
    ("PCE", "Pharmaceutical and Chemical Engineering", B, ""),
    ("MPCE", "Pharmaceutical and Chemical Engineering", M, ""),
    # --- School of Applied Technical Sciences (SATS) ---
    ("IE", "Industrial Engineering", B, ""),
    ("MME", "Mechanical and Maintenance Engineering", B, ""),
    ("MTE", "Mechatronics Engineering", B, ""),
    ("MSEM", "Engineering Management", M, ""),
    ("EIM", "Entrepreneurship and Innovation Management", M, ""),
    # --- School of Architecture and Built Environment (SABE) ---
    ("ARCH", "Architecture", B, ""),
    ("INAR", "Interior Architecture", B, ""),
    ("DVC", "Design and Visual Communication", B, ""),
    ("MARC", "Architectural Conservation", M, ""),
    ("MSP", "Spatial Planning", M, ""),
    ("MSB", "Sustainable Buildings", M, ""),
    ("PDQS", "Quantity Surveying (Professional Diploma)", D, ""),
    # --- School of Sustainable Systems Engineering (SSSE) ---
    ("SISE", "Sustainable Infrastructure Systems Engineering", B, ""),
    ("EE", "Electrical Engineering", B, ""),
    ("ENE", "Energy Engineering", B, ""),
    ("MEREE", "Environmental and Renewable Energy Engineering", M, ""),
    ("WASH", "Humanitarian Water, Sanitation and Hygiene (WaSH)", M, ""),
    ("HDCET", "Civil Engineering Technologies", D, ""),
    # --- School of Nursing (SN) ---
    ("NUR", "Nursing", B, ""),
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
        created_m = updated_m = 0
        for code, name, level, partner in MAJORS:
            _, created = Major.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "degree_level": level,
                    "partner_institution": partner,
                    "is_active": True,
                },
            )
            created_m += int(created)
            updated_m += int(not created)

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
