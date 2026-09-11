from django.db import models
from django.utils.text import slugify

from common.models import TimeStampedModel


def normalize_code(raw: str) -> str:
    """'CS 116', 'cs-116' -> 'CS116' so lookups and dedup are consistent."""
    return "".join(ch for ch in (raw or "") if ch.isalnum()).upper()


class DegreeLevel(models.TextChoices):
    DIPLOMA = "diploma", "Diploma"
    BACHELOR = "bachelor", "Bachelor"
    MASTER = "master", "Master"
    PHD = "phd", "PhD"


class Major(TimeStampedModel):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, unique=True)
    degree_level = models.CharField(
        max_length=20, choices=DegreeLevel.choices, default=DegreeLevel.BACHELOR
    )
    partner_institution = models.CharField(
        max_length=255, blank=True, help_text="e.g. PSUT, THWS for joint programs."
    )
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.code}-{self.name}")[:255]
        super().save(*args, **kwargs)


class Instructor(TimeStampedModel):
    """A lecturer / faculty member. May exist without a login account."""

    full_name = models.CharField(max_length=255)
    title = models.CharField(max_length=50, blank=True, help_text="Prof./Dr./Eng.")
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.title} {self.full_name}".strip()


class Course(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True, help_text="Normalized, e.g. CS116")
    display_code = models.CharField(max_length=20, blank=True, help_text="e.g. 'CS 116'")
    name = models.CharField(max_length=255)
    majors = models.ManyToManyField(Major, related_name="courses", blank=True)
    credit_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    level = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="100/200/300 tier"
    )
    description = models.TextField(blank=True)
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, related_name="required_by", blank=True
    )
    corequisites = models.ManyToManyField(
        "self", symmetrical=False, related_name="corequisite_of", blank=True
    )
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.display_code or self.code} — {self.name}"

    def save(self, *args, **kwargs):
        self.code = normalize_code(self.code)
        if not self.display_code:
            self.display_code = self.code
        if not self.slug:
            self.slug = slugify(f"{self.code}-{self.name}")[:255]
        super().save(*args, **kwargs)


class Term(TimeStampedModel):
    class Season(models.TextChoices):
        FIRST = "first", "First"
        SECOND = "second", "Second"
        SUMMER = "summer", "Summer"

    season = models.CharField(max_length=10, choices=Season.choices)
    year = models.PositiveIntegerField(help_text="Academic year the term starts, e.g. 2025")
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-year", "-season"]
        constraints = [
            models.UniqueConstraint(fields=["season", "year"], name="uniq_term")
        ]

    def __str__(self):
        return f"{self.get_season_display()} {self.year}"


class CourseOffering(TimeStampedModel):
    """A 'section': one course, one term, taught by instructor(s). MyGJU-like."""

    class Language(models.TextChoices):
        ENGLISH = "english", "English"
        ARABIC = "arabic", "Arabic"
        GERMAN = "german", "German"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="offerings")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="offerings")
    instructors = models.ManyToManyField(Instructor, related_name="offerings", blank=True)
    section_number = models.CharField(max_length=10, blank=True)
    campus = models.CharField(max_length=100, blank=True)
    language = models.CharField(max_length=10, choices=Language.choices, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    # Set by the Moodle importer; maps a Moodle course to our catalog.
    moodle_course_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-term__year", "course__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "term", "section_number"], name="uniq_offering"
            )
        ]

    def __str__(self):
        sec = f" §{self.section_number}" if self.section_number else ""
        return f"{self.course.display_code} — {self.term}{sec}"


class MeetingTime(TimeStampedModel):
    """A section's weekly schedule slot."""

    class Kind(models.TextChoices):
        LECTURE = "lecture", "Lecture"
        LAB = "lab", "Lab"
        TUTORIAL = "tutorial", "Tutorial"

    class Day(models.TextChoices):
        SUN = "sun", "Sunday"
        MON = "mon", "Monday"
        TUE = "tue", "Tuesday"
        WED = "wed", "Wednesday"
        THU = "thu", "Thursday"

    offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="meeting_times"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.LECTURE)
    day_of_week = models.CharField(max_length=3, choices=Day.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["day_of_week", "start_time"]

    def __str__(self):
        return f"{self.offering} {self.get_day_of_week_display()} {self.start_time}"


class ExamSchedule(TimeStampedModel):
    """A section's exam sitting."""

    class Kind(models.TextChoices):
        MIDTERM = "midterm", "Midterm"
        FINAL = "final", "Final"
        QUIZ = "quiz", "Quiz"

    offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="exams"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    starts_at = models.DateTimeField()
    room = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return f"{self.offering} {self.get_kind_display()}"
