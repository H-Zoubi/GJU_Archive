"""
Read a GJU study-plan PDF into (course code, category, requirement) rows.

Every plan checked — all 14 bachelor majors — classifies its courses with a
numbered heading above each table rather than with any column:

    1.    University Requirements
    1.1.  Compulsory                      -> university / compulsory
    1.2.  Elective                        -> university / elective
    2.    School Requirements             -> school / compulsory
    3.1.  Program Requirements (Compulsory)
    3.2.  Program Requirements (Electives)
    4.1.1 Architecture Stream Compulsory Requirements

So the top-level number gives the bucket and the wording gives compulsory vs
elective. Both are read from the heading; nothing is inferred from the code.

Where a heading names neither word (a bare "2. School Requirements"), the row
is still emitted but flagged unconfident, because the plans are inconsistent
about restating it and a silent guess is worse than a reviewable one.

Headings that carry no requirement vocabulary at all are ignored: the plans
reuse the same numbering for unrelated prose ("1. Technical Knowledge" in the
programme-objectives section), and treating those as course sections would
file the objectives list as courses.
"""
import re
from dataclasses import dataclass

import pdfplumber

from .models import ProgramCourse, normalize_code

# "1.", "3.2", "4.1.1" then a title, which runs to a colon or to line end.
# The trailing part matters: the plans write "1.2. Elective: (6 credit hours)",
# so a pattern anchored at the line end misses every elective heading.
SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+([A-Za-z][^:]{3,90}?)\s*(?::.*)?$")

# "(6 credit hours)", "(21 Credit Hours)" — a size note, not part of the name.
CREDITS_RE = re.compile(r"\s*\(\s*\d+\s*credit\s*hours?\s*\)\s*$", re.IGNORECASE)

# A heading only counts as a course section if it talks about requirements.
# This is what separates "3.2 Program Requirements (Electives)" from
# "2. Technical Skills" in the objectives preamble.
RELEVANT_RE = re.compile(
    r"requirement|compulsory|elective|mandatory|remedial|stream|track", re.IGNORECASE
)

TRACK_RE = re.compile(r"\(([^)]*\b(?:track|stream)\b[^)]*)\)", re.IGNORECASE)

# After the requirement sections, every plan repeats the whole degree as a
# semester-by-semester timetable under "Third Year / First Semester" headings.
# Those tables list the same courses again with no requirement heading of
# their own, so left alone they inherit whichever section came last — which
# silently doubled the elective counts. A year marker ends the requirements.
SCHEDULE_RE = re.compile(
    r"^(first|second|third|fourth|fifth|sixth)\s+year\b", re.IGNORECASE
)

# Course codes as the plans write them: ARB0099, CS116, MADAF 754, ME 301.
CODE_RE = re.compile(r"^[A-Z]{2,6}\s?\d{2,4}[A-Z0-9-]*$")
# Same shape, but matching just the start of a text line rather than a whole
# table cell — used when a page has no ruled table to split into cells.
CODE_AT_LINE_START_RE = re.compile(r"^([A-Z]{2,6}\s?\d{2,4}[A-Z0-9-]*)\b")

CATEGORY_BY_NUMBER = {
    "1": ProgramCourse.Category.UNIVERSITY,
    "2": ProgramCourse.Category.SCHOOL,
}


@dataclass
class PlanRow:
    code: str
    name: str
    credit_hours: int | None
    category: str
    requirement: str
    section: str
    track: str
    confident: bool
    note: str


def classify(number: str, title: str, stated=None):
    """Map a numbered heading to (category, requirement, confident, note).

    `stated` holds the requirement of every earlier heading that named one,
    keyed by section number, so a silent subsection can inherit from its
    parent: "3.1.1 Program Requirements (Common)" sits under "3.1 Program
    Requirements (Compulsory)" and means compulsory, which the subsection
    itself never repeats.
    """
    top = number.split(".")[0]
    text = title.lower()

    # The title is trusted over the number: most plans promote program
    # requirements to their own top-level "3", but International Accounting
    # nests them as "2.2 Program Requirements (Compulsory for all tracks)"
    # under the same "2" as School Requirements. Reading the words avoids
    # filing those as school requirements just because of where they sit.
    if "remedial" in text:
        category = ProgramCourse.Category.REMEDIAL
    elif "program" in text or "programme" in text:
        category = ProgramCourse.Category.PROGRAM
    elif "school" in text:
        category = ProgramCourse.Category.SCHOOL
    elif "university" in text:
        category = ProgramCourse.Category.UNIVERSITY
    else:
        # No category word at all — a bare "1.1 Compulsory" under
        # "1 University Requirements". Fall back to the top-level number.
        category = CATEGORY_BY_NUMBER.get(top, ProgramCourse.Category.PROGRAM)

    has_elective = "elective" in text
    has_compulsory = "compulsory" in text or "mandatory" in text

    if has_elective and not has_compulsory:
        return category, ProgramCourse.Requirement.ELECTIVE, True, ""
    if has_compulsory and not has_elective:
        return category, ProgramCourse.Requirement.COMPULSORY, True, ""
    if has_compulsory and has_elective:
        # e.g. a summary table headed "Compulsory Elective Total".
        return (category, ProgramCourse.Requirement.COMPULSORY, False,
                "heading names both compulsory and elective")

    # Silent heading. Inherit from the nearest numbered ancestor that did
    # say, e.g. "3.1.1" from "3.1".
    parts = number.split(".")
    for depth in range(len(parts) - 1, 0, -1):
        parent = ".".join(parts[:depth])
        if stated and parent in stated:
            return (category, stated[parent], True,
                    f"inherited from section {parent}")

    # A top-level "2. School Requirements" with nothing above it. Every plan
    # gives its electives their own numbered heading, so an unqualified
    # requirements section is the compulsory list; the document never states
    # it outright, so say where this came from.
    return (category, ProgramCourse.Requirement.COMPULSORY, True,
            "section names no requirement type; electives are listed separately")


def _int_or_none(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def parse_plan(path):
    """Yield PlanRow for every course line in the PDF at `path`."""
    rows = []
    current = None  # (number, title, category, requirement, confident, note)
    stated = {}  # section number -> requirement, for headings that said one

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            # Headings come from the text layer, courses from the tables, and
            # a page routinely holds several of each — "3.1 Compulsory" with
            # its table, then "3.2 Electives" with its own. So both are
            # collected with their vertical position and each table takes the
            # nearest heading above it. A heading also carries to later pages
            # until the next one, since long tables (Architecture's electives)
            # run for several pages.
            headings = []
            schedule = False
            for line in page.extract_text_lines() or []:
                text = line["text"].strip()
                if SCHEDULE_RE.match(text):
                    schedule = True
                match = SECTION_RE.match(text)
                if not match:
                    continue
                title = CREDITS_RE.sub("", match.group(2)).strip()
                if not (title and RELEVANT_RE.search(title)):
                    continue
                number = match.group(1)
                category, requirement, confident, note = classify(
                    number, title, stated
                )
                if not note:
                    # No note means the heading named the type itself, so it
                    # is sound for a subsection to inherit from.
                    stated[number] = requirement
                headings.append((
                    line["top"],
                    (number, title, category, requirement, confident, note),
                ))
            headings.sort()

            # The timetable always follows the requirement sections, so the
            # first page that opens one with no requirement heading of its own
            # marks the end of anything worth reading.
            if schedule and not headings and rows:
                break

            tables = page.find_tables()
            for table in tables:
                top = table.bbox[1]
                above = [h for position, h in headings if position <= top]
                section = above[-1] if above else current
                if section is None:
                    continue

                number, title, category, requirement, confident, note = section
                track_match = TRACK_RE.search(title)
                track = track_match.group(1).strip() if track_match else ""

                for row in table.extract():
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    if not cells:
                        continue
                    code = cells[0]
                    if not CODE_RE.match(code.upper()):
                        continue  # header, totals row, or prose
                    rows.append(PlanRow(
                        code=normalize_code(code),
                        name=cells[1] if len(cells) > 1 else "",
                        credit_hours=_int_or_none(cells[2] if len(cells) > 2 else ""),
                        category=category,
                        requirement=requirement,
                        section=f"{number} {title}"[:200],
                        track=track[:120],
                        confident=confident,
                        note=note,
                    ))

            # Some plans (Computer Science) print these tables without ruled
            # borders, so pdfplumber's grid detector finds nothing and the
            # ruled-table pass above silently loses every course on the page.
            # Falling back to scanning text lines for a leading course code
            # catches those, at the cost of not knowing the column layout —
            # so these rows are always marked unconfident for a human to spot
            # check, regardless of how sure the heading itself was.
            if not tables:
                for line in page.extract_text_lines() or []:
                    text = line["text"].strip()
                    match = CODE_AT_LINE_START_RE.match(text)
                    if not match:
                        continue
                    top = line["top"]
                    above = [h for position, h in headings if position <= top]
                    section = above[-1] if above else current
                    if section is None:
                        continue

                    number, title, category, requirement, _, note = section
                    track_match = TRACK_RE.search(title)
                    track = track_match.group(1).strip() if track_match else ""
                    fallback_note = "no ruled table on this page; verify against the PDF"
                    rows.append(PlanRow(
                        code=normalize_code(match.group(1)),
                        name="",
                        credit_hours=None,
                        category=category,
                        requirement=requirement,
                        section=f"{number} {title}"[:200],
                        track=track[:120],
                        confident=False,
                        note=f"{note}; {fallback_note}" if note else fallback_note,
                    ))

            if headings:
                current = headings[-1][1]
    return rows
