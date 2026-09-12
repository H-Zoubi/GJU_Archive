"""
Populate ProgramCourse from the downloaded study-plan PDFs.

    python manage.py fetch_study_plans     # get the PDFs first
    python manage.py import_study_plans
    python manage.py import_study_plans --dry-run --major CE

Courses named by a plan but absent from the catalogue are reported, not
created: the catalogue comes from MyGJU section listings, and a plan naming
something MyGJU has never offered usually means a renamed or retired code
worth looking at rather than a new course worth inventing.
"""
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from academics.models import Course, Major, ProgramCourse
from academics.study_plans import parse_plan

PLANS_DIR = Path(__file__).resolve().parents[3] / "data" / "study_plans"


class Command(BaseCommand):
    help = "Import mandatory/elective classification from study-plan PDFs."

    def add_arguments(self, parser):
        parser.add_argument("--major", help="Only this major code, e.g. CE.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Parse and report without writing.")

    def handle(self, *args, **options):
        if not PLANS_DIR.exists():
            self.stderr.write(self.style.ERROR(
                f"{PLANS_DIR} not found — run: manage.py fetch_study_plans"
            ))
            return

        wanted = (options["major"] or "").upper()
        paths = sorted(PLANS_DIR.glob("*.pdf"))
        if wanted:
            paths = [p for p in paths if p.stem.upper() == wanted]
            if not paths:
                self.stderr.write(self.style.ERROR(f"No plan PDF for {wanted}."))
                return

        total_created = total_unknown = total_flagged = 0

        for path in paths:
            code = path.stem
            try:
                major = Major.objects.get(code__iexact=code)
            except Major.DoesNotExist:
                self.stderr.write(self.style.WARNING(
                    f"  {code:6} SKIPPED — no Major with this code"
                ))
                continue

            rows = parse_plan(path)
            unknown = set()
            created = flagged = 0

            with transaction.atomic():
                if not options["dry_run"]:
                    ProgramCourse.objects.filter(major=major).delete()

                for row in rows:
                    course = Course.objects.filter(code=row.code).first()
                    if course is None:
                        unknown.add(row.code)
                        continue
                    if not row.confident:
                        flagged += 1
                    if options["dry_run"]:
                        created += 1
                        continue

                    existing = ProgramCourse.objects.filter(
                        major=major, course=course, track=row.track
                    ).first()
                    if existing is not None:
                        # Plans list some compulsory courses again inside an
                        # elective menu (a track elective that another track
                        # requires). Being required somewhere is the stronger
                        # claim, so never let an elective row overwrite it.
                        if (existing.requirement == ProgramCourse.Requirement.COMPULSORY
                                and row.requirement != existing.requirement):
                            continue
                        for field, value in (
                            ("category", row.category),
                            ("requirement", row.requirement),
                            ("section", row.section),
                            ("confident", row.confident),
                            ("note", row.note),
                        ):
                            setattr(existing, field, value)
                        existing.save()
                        continue

                    ProgramCourse.objects.create(
                        major=major, course=course, track=row.track,
                        category=row.category, requirement=row.requirement,
                        section=row.section, confident=row.confident,
                        note=row.note,
                    )
                    created += 1

                if options["dry_run"]:
                    transaction.set_rollback(True)

            compulsory = sum(
                1 for r in rows if r.requirement == ProgramCourse.Requirement.COMPULSORY
            )
            self.stdout.write(
                f"  {code:6} {len(rows):4} rows  "
                f"{compulsory:3} compulsory  {len(rows) - compulsory:3} elective  "
                f"{created:4} saved  {flagged:3} flagged  "
                f"{len(unknown):3} unknown codes"
            )
            if unknown:
                sample = ", ".join(sorted(unknown)[:12])
                self.stdout.write(f"           not in catalogue: {sample}")

            total_created += created
            total_unknown += len(unknown)
            total_flagged += flagged

        verb = "would save" if options["dry_run"] else "saved"
        self.stdout.write(
            f"\n{verb} {total_created} plan rows; "
            f"{total_flagged} need review; {total_unknown} unmatched codes."
        )
