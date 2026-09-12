"""
Parse a saved MyGJU "Course Sections" page (HTML) into section records.

Saving the rendered page is more reliable than copying its text:

* Every ``<tr>`` carries ``data-rk="<year>.<semester>.<n>.<id>"``, so each row
  states its own term. We never have to trust the filename or the page's
  filter dropdowns, which keep whatever state the form was left in (all three
  of our exports say "All" even though each holds exactly one semester).
* Instructor, days/times and room are nested ``<table>``s whose rows align by
  index, so a section's days pair with its rooms positionally instead of by
  guessing where one run of lines ends and the next begins.

Row layout (top-level ``<td>``, 13 cells):

    0 radio  1 code  2 name  3 section  4 instructors  5 days/times  6 rooms
    7 credit  8 financial  9 capacity  10 enrolled  11 block  12 packages
"""
import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup

# data-rk semester component -> Term.Season value.
SEASONS = {"1": "first", "2": "second", "3": "summer"}

DAYS = {
    "sun": "sun",
    "mon": "mon",
    "tue": "tue",
    "wed": "wed",
    "thu": "thu",
    "fri": "fri",
    "sat": "sat",
}

# "Mon 08:30 AM - 10:00 AM" with an optional trailing "Online".
MEETING_RE = re.compile(
    r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+"
    r"(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*"
    r"(\d{1,2}:\d{2}\s*[AP]M)"
    r"(?P<online>\s+Online)?\s*$",
    re.IGNORECASE,
)

RK_RE = re.compile(r"^(\d{4})\.([123])\.")


@dataclass
class Meeting:
    day: str
    start: object
    end: object
    room: str = ""
    online: bool = False


@dataclass
class Section:
    code: str
    name: str
    section: str
    year: int
    season: str
    instructors: list = field(default_factory=list)
    meetings: list = field(default_factory=list)
    credit_hours: int = None
    capacity: int = None


def _text(node):
    return " ".join(node.get_text(" ", strip=True).split())


def _inner_rows(cell):
    """Rows of a nested table, dropping the empty header row MyGJU emits."""
    return [t for t in (_text(r) for r in cell.find_all("tr")) if t]


def _time(raw):
    return datetime.strptime(raw.replace(" ", "").upper(), "%I:%M%p").time()


def _int(raw):
    raw = raw.strip()
    return int(raw) if raw.isdigit() else None


def is_no_instructor(value):
    """'N.A.', 'N.A' and 'N. .' all mean no instructor is assigned."""
    return re.sub(r"[.\s]", "", value).upper() in {"", "N", "NA"}


def parse_sections(html):
    """Yield a Section for every data row in the saved page."""
    soup = BeautifulSoup(html, "lxml")
    tbody = soup.find("tbody", id=re.compile(r"sections_tbl_data"))
    if tbody is None:
        return []

    sections = []
    for row in tbody.find_all("tr", recursive=False):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 13:
            continue

        match = RK_RE.match(row.get("data-rk") or "")
        if not match:
            continue
        year, season = int(match.group(1)), SEASONS[match.group(2)]

        code = _text(cells[1])
        name = _text(cells[2])
        section_no = _text(cells[3])
        if not code or not section_no:
            continue

        instructors = [
            n for n in _inner_rows(cells[4]) if not is_no_instructor(n)
        ]

        # Days and rooms are parallel nested tables: the n-th day happens in
        # the n-th room. A day we cannot parse still consumes its room slot.
        rooms = _inner_rows(cells[6])
        meetings = []
        for index, raw in enumerate(_inner_rows(cells[5])):
            meeting = MEETING_RE.match(raw)
            if not meeting:
                continue
            try:
                start, end = _time(meeting.group(2)), _time(meeting.group(3))
            except ValueError:
                continue
            meetings.append(
                Meeting(
                    day=DAYS[meeting.group(1).lower()],
                    start=start,
                    end=end,
                    room=rooms[index] if index < len(rooms) else "",
                    online=bool(meeting.group("online")),
                )
            )

        sections.append(
            Section(
                code=code,
                name=name,
                section=section_no,
                year=year,
                season=season,
                instructors=instructors,
                meetings=meetings,
                credit_hours=_int(_text(cells[7])),
                capacity=_int(_text(cells[9])),
            )
        )

    return sections
