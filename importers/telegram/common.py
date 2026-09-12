"""
Shared bits between parse.py and apply.py.

Both are plain scripts with no Django and no database of their own: this
importer is a separate OS-level job (see the resources.views_ingest module
in the backend for the API it talks to), so it only ever knows the archive
through HTTP.
"""
import re

# Course codes as GJU writes them: CS116, MADAF 754, ME 301. Kept in sync by
# eye with academics.models.normalize_code / code_prefix in the backend --
# there is no import across the two since this script has no Django on its
# path, but the pattern only needs to be loose enough for a human reviewer to
# fix up, not perfectly correct.
COURSE_RE = re.compile(r"\b([A-Z]{2,6})\s?-?(\d{2,4})\b")

TYPE_KEYWORDS = [
    # Checked in order; the first match wins, so put more specific words
    # (midterm before "exam") first only where it matters for logging --
    # they all resolve to the same ResourceType.EXAM here.
    ("exam", ("exam", "midterm", "final", "quiz")),
    ("slides", ("slides", "lecture", "ppt", "presentation")),
    ("assignment", ("assignment", "homework", "hw", "project")),
    ("lab", ("lab",)),
    ("notes", ("notes", "summary", "summaries", "cheat sheet")),
    ("book", ("book", "textbook")),
]


def normalize_code(raw: str) -> str:
    return "".join(ch for ch in (raw or "") if ch.isalnum()).upper()


def guess_course(text: str) -> str:
    match = COURSE_RE.search((text or "").upper())
    return f"{match.group(1)}{match.group(2)}" if match else ""


def guess_type(text: str) -> str:
    lowered = (text or "").lower()
    for resource_type, keywords in TYPE_KEYWORDS:
        if any(word in lowered for word in keywords):
            return resource_type
    return "other"


def flatten_text(value) -> str:
    """Telegram's export writes `text` as either a string or a list of runs
    (plain strings mixed with {"type": ..., "text": ...} dicts for
    links/bold/etc.). Either way, we just want the plain words."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "".join(parts)
    return ""
