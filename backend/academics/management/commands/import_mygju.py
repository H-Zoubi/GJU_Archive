"""
Import GJU course sections from a MyGJU "Course Sections" page.

The input is the plain text of the results table (select the page and copy, or
save the rendered text). Each section is one record shaped like:

    CS223<TAB>Data Structures<TAB>2<TAB>
    Kholoud Nairokh
    Hend Bataineh
    Asma Alkhraibat
    Mon<TAB>10:00 AM-<TAB>11:30 AM<TAB>
    Tue<TAB>02:30 PM-<TAB>04:30 PM<TAB>
    Wed<TAB>10:00 AM-<TAB>11:30 AM<TAB>
    M328
    M VIRTUAL 11
    M328
    3<TAB>3<TAB>34<TAB>0<TAB>Unblocked<TAB>No

i.e. header, then instructor name(s), then one line per meeting day, then one
room line per meeting day, then the stats row. "N.A." means no instructor.

The page itself states the year/semester, which we read from the filter block;
pass --season/--year to override. A page exported with Semester = "All" mixes
terms and cannot be attributed, so a season must be given explicitly.

    python manage.py import_mygju data/mygju_first_2026.txt
    python manage.py import_mygju data/mygju_all_2025.txt --season first --year 2025

Idempotent: re-running replaces the offering's instructors and meeting times.
Live seat counts are deliberately not imported (they change by the minute).
"""
import re
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from academics.models import (
    Course,
    CourseOffering,
    Instructor,
    MeetingTime,
    Term,
    normalize_code,
)

DAY_CODES = {
    "sun": MeetingTime.Day.SUN,
    "mon": MeetingTime.Day.MON,
    "tue": MeetingTime.Day.TUE,
    "wed": MeetingTime.Day.WED,
    "thu": MeetingTime.Day.THU,
    "fri": MeetingTime.Day.FRI,
    "sat": MeetingTime.Day.SAT,
}

DAY_RE = re.compile(
    r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\b\s*"
    r"(\d{1,2}:\d{2}\s*[AP]M)\s*-?\s*"
    r"(\d{1,2}:\d{2}\s*[AP]M)",
    re.IGNORECASE,
)
STATS_RE = re.compile(
    r"^(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(Unblocked|Blocked)\s+(Yes|No)\s*$"
)
YEAR_RE = re.compile(r"^\s*(\d{4})\s*/\s*\d{4}\s*$")
SEASON_WORDS = {"first": "first", "second": "second", "summer": "summer"}

def is_no_instructor(value):
    """'N.A.', 'N.A' and 'N. .' all mean no instructor is assigned."""
    return re.sub(r"[.\s]", "", value).upper() in {"", "N", "NA"}


def parse_time(raw):
    return datetime.strptime(raw.replace(" ", "").upper(), "%I:%M%p").time()


def clean_instructor(name):
    return re.sub(r"\s+", " ", name.replace('"', "")).strip()


def parse_header(line):
    """A header row is CODE / NAME / SECTION separated by tabs."""
    parts = line.split("\t")
    if len(parts) < 3:
        return None
    code, name, section = (p.strip() for p in parts[:3])
    if not code or not name or not section.isdigit():
        return None
    if not code[0].isupper():  # stats rows start with a digit
        return None
    return code, name, section


class Record:
    def __init__(self, code, name, section):
        self.code = code
        self.name = name
        self.section = section
        self.instructors = []
        self.days = []      # (day_code, start, end)
        self.rooms = []
        self.stats = None   # (credit, financial, capacity, enrolled)

    @property
    def complete(self):
        return self.stats is not None


def parse(text):
    """Yield Record objects, plus (year, season) detected from the filter block."""
    lines = text.splitlines()
    year = season = None
    records = []
    current = None

    for index, raw in enumerate(lines):
        line = raw.rstrip()
        if not line.strip():
            continue

        header = parse_header(line)
        if header:
            current = Record(*header)
            records.append(current)
            continue

        # Filter block: "Year :" then "2026/2027"; "Semester :*" then "First".
        if current is None:
            stripped = line.strip()
            if YEAR_RE.match(stripped) and year is None:
                year = int(YEAR_RE.match(stripped).group(1))
            elif stripped.lower() in SEASON_WORDS and season is None:
                season = SEASON_WORDS[stripped.lower()]
            continue

        if current.complete:
            continue  # trailing footer lines after the last record

        stats = STATS_RE.match(line.strip())
        if stats:
            current.stats = (
                int(stats.group(1)),
                int(stats.group(2)),
                int(stats.group(3)),
                int(stats.group(4)),
            )
            continue

        day = DAY_RE.match(line.strip())
        if day:
            try:
                current.days.append(
                    (
                        DAY_CODES[day.group(1).lower()],
                        parse_time(day.group(2)),
                        parse_time(day.group(3)),
                    )
                )
            except ValueError:
                pass
            continue

        value = line.split("\t")[0].strip()
        if not value:
            continue
        if current.days:
            current.rooms.append(value)          # rooms follow the day rows
        elif not is_no_instructor(value):
            current.instructors.append(clean_instructor(value))

    return records, year, season


class Command(BaseCommand):
    help = "Import course sections from a MyGJU Course Sections page."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Text file of the MyGJU results table.")
        parser.add_argument("--season", choices=sorted(SEASON_WORDS))
        parser.add_argument("--year", type=int, help="Academic year the term starts.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report without writing to the database.",
        )

    def handle(self, *args, **options):
        with open(options["path"], encoding="utf-8", errors="replace") as handle:
            text = handle.read()

        if "sections_tbl_data" in text:
            return self._handle_html(text, options)

        records, page_year, page_season = parse(text)
        year = options["year"] or page_year
        season = options["season"] or page_season

        parsed = [r for r in records if r.complete]
        skipped = len(records) - len(parsed)
        self.stdout.write(
            f"Parsed {len(parsed)} sections"
            + (f" ({skipped} incomplete, skipped)" if skipped else "")
        )
        if not parsed:
            raise CommandError("No sections found — is this the Course Sections page?")

        if not season:
            raise CommandError(
                "Could not determine the semester (the page may say 'All'). "
                "Pass --season first|second|summer."
            )
        if not year:
            raise CommandError("Could not determine the year. Pass --year.")

        self.stdout.write(f"Term: {season} {year}")
        if options["dry_run"]:
            self._preview(parsed)
            return

        term, _ = Term.objects.get_or_create(season=season, year=year)
        self._load(parsed, term)

    def _handle_html(self, html, options):
        """Saved MyGJU page: every row states its own term via data-rk."""
        from academics.mygju_html import parse_sections

        sections = parse_sections(html)
        if not sections:
            raise CommandError(
                "No sections found — is this a saved Course Sections page?"
            )

        by_term = {}
        for section in sections:
            by_term.setdefault((section.year, section.season), []).append(section)

        self.stdout.write(f"Parsed {len(sections)} sections (HTML)")
        for (year, season), group in sorted(by_term.items()):
            self.stdout.write(f"  {season} {year}: {len(group)} sections")

        # A CLI override here would silently mislabel rows, since the page can
        # hold several terms. Refuse rather than write the wrong semester.
        if options["season"] or options["year"]:
            raise CommandError(
                "This page states its own term per row; drop --season/--year."
            )

        if options["dry_run"]:
            for section in sections[:5]:
                self.stdout.write(
                    f"  {section.code} sec {section.section} {section.name!r} "
                    f"{section.season} {section.year} "
                    f"instructors={section.instructors} "
                    f"meetings={len(section.meetings)}"
                )
            self.stdout.write(self.style.WARNING("Dry run — nothing written."))
            return

        for (year, season), group in sorted(by_term.items()):
            term, _ = Term.objects.get_or_create(season=season, year=year)
            self._load_sections(group, term)

    @transaction.atomic
    def _load_sections(self, sections, term):
        courses = instructors = offerings = meetings = 0

        for section in sections:
            code = normalize_code(section.code)
            course, created = Course.objects.update_or_create(
                code=code,
                defaults={
                    "display_code": section.code,
                    "name": section.name,
                    "credit_hours": section.credit_hours or None,
                },
            )
            courses += int(created)

            people = []
            for name in section.instructors:
                instructor, made = Instructor.objects.get_or_create(full_name=name)
                instructors += int(made)
                people.append(instructor)

            offering, created = CourseOffering.objects.update_or_create(
                course=course,
                term=term,
                section_number=section.section,
                defaults={"capacity": section.capacity},
            )
            offerings += int(created)
            offering.instructors.set(people)

            # Rebuild the schedule so re-importing a corrected page stays clean.
            offering.meeting_times.all().delete()
            is_lab = "lab" in section.name.lower()
            for meeting in section.meetings:
                MeetingTime.objects.create(
                    offering=offering,
                    kind=MeetingTime.Kind.LAB if is_lab else MeetingTime.Kind.LECTURE,
                    day_of_week=meeting.day,
                    start_time=meeting.start,
                    end_time=meeting.end,
                    room=meeting.room,
                )
                meetings += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  {term}: +{courses} courses, +{instructors} instructors, "
                f"+{offerings} offerings, {meetings} meeting times"
            )
        )

    def _preview(self, records):
        for record in records[:5]:
            self.stdout.write(
                f"  {record.code} sec {record.section} {record.name!r} "
                f"instructors={record.instructors} days={len(record.days)} "
                f"rooms={len(record.rooms)} stats={record.stats}"
            )
        self.stdout.write(self.style.WARNING("Dry run — nothing written."))

    @transaction.atomic
    def _load(self, records, term):
        courses = instructors = offerings = meetings = 0
        seen_courses, seen_instructors = set(), set()

        for record in records:
            code = normalize_code(record.code)
            credit = record.stats[0] if record.stats else None
            course, created = Course.objects.update_or_create(
                code=code,
                defaults={
                    "display_code": record.code,
                    "name": record.name,
                    "credit_hours": credit or None,
                },
            )
            if code not in seen_courses:
                seen_courses.add(code)
                courses += int(created)

            people = []
            for name in record.instructors:
                instructor, created = Instructor.objects.get_or_create(full_name=name)
                if name not in seen_instructors:
                    seen_instructors.add(name)
                    instructors += int(created)
                people.append(instructor)

            offering, created = CourseOffering.objects.update_or_create(
                course=course,
                term=term,
                section_number=record.section,
                defaults={"capacity": record.stats[2] if record.stats else None},
            )
            offerings += int(created)
            offering.instructors.set(people)

            # Rebuild the schedule so re-running the import stays clean.
            offering.meeting_times.all().delete()
            is_lab = "lab" in record.name.lower()
            for position, (day, start, end) in enumerate(record.days):
                MeetingTime.objects.create(
                    offering=offering,
                    kind=MeetingTime.Kind.LAB if is_lab else MeetingTime.Kind.LECTURE,
                    day_of_week=day,
                    start_time=start,
                    end_time=end,
                    room=record.rooms[position] if position < len(record.rooms) else "",
                )
                meetings += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"New courses {courses}, new instructors {instructors}, "
                f"new offerings {offerings}, meeting times {meetings}."
            )
        )
        self.stdout.write(
            f"Totals — courses {Course.objects.count()}, "
            f"instructors {Instructor.objects.count()}, "
            f"offerings {CourseOffering.objects.count()}."
        )
