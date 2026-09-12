"""
Download GJU study-plan PDFs — one per major, newest regular track.

The plans are not linked from the school pages. They live at

    /sites/default/files/<Department>/programs/<file>.pdf

and are reached school -> department -> /content/programs-<id> -> PDF, which is
why searching for "study plan" link text finds almost nothing.

Most departments publish several: different years (2012 through 2025), Dual
Studies alongside Regular, thesis vs comprehensive for masters, Arabic
editions, and flowchart "tree plans" that hold no course table. We keep the
newest Regular bachelor plan per major and ignore the rest; older intakes
follow older plans, which we can add later if students ask.

    python manage.py fetch_study_plans            # download
    python manage.py fetch_study_plans --list     # show choices, download none
"""
import re
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand

BASE = "https://www.gju.edu.jo"
DEST = Path(__file__).resolve().parents[3] / "data" / "study_plans"

# major code -> (label, path). Newest regular bachelor plan for each.
PLANS = {
    "CE": ("Computer Engineering 2023/24",
           "/sites/default/files/Computer Engineering/programs/"
           "study_plan_all_tracks_2023-2024.pdf"),
    "MME": ("Mechanical and Maintenance 2023",
            "/sites/default/files/Mechanical and Maintenance Engineering/"
            "programs/mech_study_plan_2023.pdf"),
    "IE": ("Industrial Engineering 2023",
           "/sites/default/files/Industrial Engineering/programs/"
           "ie_regular_study_plan_2023_r18.pdf"),
    "MTE": ("Mechatronics Engineering 2024",
            "/sites/default/files/Mechatronics Engineering/programs/"
            "me_study_plan_2024_r1_-_20260416.pdf"),
    "SISE": ("Civil and Environmental 2023",
             "/sites/default/files/Departments of Civil &amp; Environmental "
             "Engineering/programs/cee_study_plan_2023_0.pdf"),
    "ENE": ("Energy Engineering 2025",
            "/sites/default/files/Electrical and Energy Engineering/programs/"
            "2025_ene_studyplan.pdf"),
    "EE": ("Electrical Engineering 2025",
           "/sites/default/files/Electrical and Energy Engineering/programs/"
           "2025_ee_studyplan.pdf"),
    "DMKT": ("Digital Marketing 2024",
             "/sites/default/files/Management Sciences/programs/"
             "digital_marketing_study_plan_22_08_2024.pdf"),
    "ARCH": ("Architecture 2022",
             "/sites/default/files/Department of Architecture and Interior "
             "Architecture/programs/bachelor_degree_regular_study_plan_2021_2022.pdf"),
    "DVC": ("Design and Visual Communication 2024",
            "/sites/default/files/Department of Design and Visual "
            "Communication/programs/"
            "design_and_visual_comunication_studyplan2024_22-07-2025.pdf"),
    "BME": ("Biomedical Engineering 2023/24",
            "/sites/default/files/Biomedical Engineering/programs/"
            "bme_study_plan_2023-2024_finalversion_7_4_2025.pdf"),
    "PCE": ("Pharmaceutical and Chemical 2023",
            "/sites/default/files/Pharmaceutical &amp; Chemical Engineering/"
            "programs/pce_study_plan_2023_updated_23.9.2023_nr.7.7.2025.pdf"),
    "GEBC": ("German and English for Business 2023/24",
             "/sites/default/files/Department of Languages/programs/"
             "german_and_english_for_business_and_communication_study_plan_"
             "2023-2024.pdf"),
    "TRANS": ("Translation 2023/24",
              "/sites/default/files/Department of Languages/programs/"
              "translation_german-english-arabic_study_plan_2023-2024.pdf"),
    "CS": ("Computer Science 2023/24",
           "/sites/default/files/Computer Science/programs/"
           "study_plan_all_tracks_2023-2024_updated.pdf"),
    "IA": ("International Accounting regular",
           "/sites/default/files/International Accounting/programs/"
           "8_international_accounting_reqular.pdf"),
    "LS": ("Logistics Sciences regular",
           "/sites/default/files/Logistics Sciences/programs/"
           "6_logistics_regular.pdf"),
    "MGTS": ("Management Sciences regular",
             "/sites/default/files/Management Sciences/programs/"
             "2_management_sciences_regular.pdf"),
    "BIDA": ("Business Intelligence and Data Analytics regular",
             "/sites/default/files/Management Sciences/programs/"
             "4_bida_regular.pdf"),
    "NUR": ("Nursing v16",
            "/sites/default/files/Nursing Sciences/programs/"
            "nursing_study_plan-v16.0-_21january_2026.pdf"),
}

# GDMI (Game Design and Media Informatics) is a track inside the Computer
# Science plan, not a plan of its own — there is nothing to fetch for it.


def encode(path):
    """Percent-encode the paths above for the wire.

    Two departments have an ampersand in their name, and at some point the
    site wrote the *HTML-escaped* form into the filesystem: the directory is
    literally named "Pharmaceutical &amp; Chemical Engineering". So the paths
    here keep the "&amp;" verbatim and we escape it as ordinary text — do not
    "fix" them to "&", which 404s.
    """
    return quote(path, safe="/")


class Command(BaseCommand):
    help = "Download one study-plan PDF per major (newest regular track)."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true",
                            help="Print the chosen plans without downloading.")

    def handle(self, *args, **options):
        if options["list"]:
            for code, (label, path) in sorted(PLANS.items()):
                self.stdout.write(f"  {code:6} {label:42} {path.split('/')[-1]}")
            return

        DEST.mkdir(parents=True, exist_ok=True)
        ok = failed = 0
        for code, (label, path) in sorted(PLANS.items()):
            url = BASE + encode(path)
            target = DEST / f"{code}.pdf"
            try:
                request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(request, timeout=45) as response:
                    body = response.read()
                if not body.startswith(b"%PDF"):
                    raise ValueError(f"not a PDF ({body[:16]!r})")
                target.write_bytes(body)
                size = len(body) / 1024
                self.stdout.write(
                    self.style.SUCCESS(f"  {code:6} {size:7.0f} KB  {label}")
                )
                ok += 1
            except Exception as error:  # noqa: BLE001 - report and continue
                self.stdout.write(
                    self.style.ERROR(f"  {code:6} FAILED  {label}: {error}")
                )
                failed += 1

        self.stdout.write(f"\nDownloaded {ok}, failed {failed}, into {DEST}")
