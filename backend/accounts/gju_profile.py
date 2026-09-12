"""
Parses MyGJU's student profile page
(faces/student_view/profile/student_profile.xhtml) for just the fields GJU
Archive actually models.

Deliberately narrow: that page also carries national ID, birth date, home
address, and parent contact numbers -- none of which this app has any use
for or business storing. Only pull what StudentProfile has fields for (see
accounts/models.py) -- major and entry year.
"""
from bs4 import BeautifulSoup

PROFILE_URL = "https://mygju.gju.edu.jo/faces/student_view/profile/student_profile.xhtml"


def parse_profile(html: str) -> dict:
    """Returns {"major_name": str, "entry_year": int | None}."""
    soup = BeautifulSoup(html, "lxml")

    def field(element_id: str) -> str:
        el = soup.find(id=element_id)
        return el.get_text(strip=True) if el else ""

    entry_year_text = field("form:enrolYear")

    return {
        "major_name": field("form:major"),
        "entry_year": int(entry_year_text) if entry_year_text.isdigit() else None,
    }
