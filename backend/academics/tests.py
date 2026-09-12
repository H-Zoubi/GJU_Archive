"""
Tests for study-plan classification and the major/requirement browse filter.

The PDFs are not parsed here — pdfplumber's output is its own concern. What
is pinned down is the reading of a heading, which is where the compulsory vs
elective decision is actually made, and the queryset rules that decide which
courses a student sees for their major.
"""
from django.test import TestCase
from django.urls import reverse

from .models import Course, Major, ProgramCourse, Subject
from .study_plans import classify


class ClassifyHeadingTests(TestCase):
    def test_reads_the_type_the_heading_states(self):
        category, requirement, confident, note = classify("1.2", "Elective")
        self.assertEqual(category, ProgramCourse.Category.UNIVERSITY)
        self.assertEqual(requirement, ProgramCourse.Requirement.ELECTIVE)
        self.assertTrue(confident)
        self.assertEqual(note, "")

    def test_top_level_number_selects_the_bucket(self):
        self.assertEqual(classify("2", "School Requirements (Compulsory)")[0],
                         ProgramCourse.Category.SCHOOL)
        self.assertEqual(classify("3.1", "Program Requirements (Compulsory)")[0],
                         ProgramCourse.Category.PROGRAM)

    def test_subsection_inherits_from_its_parent(self):
        # "3.1.1 Program Requirements (Common)" says nothing itself; the
        # plan's "3.1 ... (Compulsory)" above it does.
        stated = {"3.1": ProgramCourse.Requirement.COMPULSORY}
        _, requirement, confident, note = classify(
            "3.1.1", "Program Requirements (Common)", stated
        )
        self.assertEqual(requirement, ProgramCourse.Requirement.COMPULSORY)
        self.assertTrue(confident)
        self.assertIn("3.1", note)

    def test_unqualified_section_is_compulsory_and_says_why(self):
        _, requirement, _, note = classify("2", "School Requirements")
        self.assertEqual(requirement, ProgramCourse.Requirement.COMPULSORY)
        self.assertTrue(note)

    def test_elective_wins_when_a_parent_said_compulsory(self):
        # An explicit word in the heading must beat an inherited default.
        stated = {"3": ProgramCourse.Requirement.COMPULSORY}
        _, requirement, _, _ = classify(
            "3.2", "Program Requirements (Electives)", stated
        )
        self.assertEqual(requirement, ProgramCourse.Requirement.ELECTIVE)


class MajorBrowseTests(TestCase):
    def setUp(self):
        self.major = Major.objects.create(code="CE", name="Computer Engineering")
        self.other = Major.objects.create(code="IE", name="Industrial Engineering")
        german = Subject.objects.create(name="German", is_university_wide=True)

        self.core = Course.objects.create(code="CE201", name="Digital Logic")
        self.core.majors.add(self.major)
        # An elective the CE plan names but whose code prefix is CS, so the
        # prefix heuristic alone would never place it in CE.
        self.elective = Course.objects.create(code="CS330", name="Image Understanding")
        self.shared = Course.objects.create(code="GERL101B1", name="German I",
                                            subject=german)
        self.unrelated = Course.objects.create(code="IE0111", name="Work Study")
        self.unrelated.majors.add(self.other)

        ProgramCourse.objects.create(
            major=self.major, course=self.core,
            category=ProgramCourse.Category.PROGRAM,
            requirement=ProgramCourse.Requirement.COMPULSORY,
        )
        ProgramCourse.objects.create(
            major=self.major, course=self.elective,
            category=ProgramCourse.Category.PROGRAM,
            requirement=ProgramCourse.Requirement.ELECTIVE,
        )

    def get(self, **params):
        response = self.client.get(reverse("course-list"), params)
        self.assertEqual(response.status_code, 200)
        return {row["code"]: row for row in response.json()["results"]}

    def test_plan_membership_includes_a_course_the_prefix_would_miss(self):
        rows = self.get(major=self.major.slug)
        self.assertIn("CS330", rows)
        self.assertEqual(rows["CS330"]["requirement"], "elective")

    def test_university_wide_courses_stay_visible(self):
        self.assertIn("GERL101B1", self.get(major=self.major.slug))

    def test_other_majors_courses_are_excluded(self):
        self.assertNotIn("IE0111", self.get(major=self.major.slug))

    def test_requirement_filter(self):
        self.assertEqual(
            set(self.get(major=self.major.slug, requirement="compulsory")),
            {"CE201"},
        )
        self.assertEqual(
            set(self.get(major=self.major.slug, requirement="elective")),
            {"CS330"},
        )

    def test_requirement_is_null_without_a_major(self):
        # "Compulsory" is meaningless until you say compulsory for whom.
        self.assertIsNone(self.get()["CE201"]["requirement"])

    def test_course_outside_the_plan_is_not_called_elective(self):
        self.assertIsNone(self.get(major=self.major.slug)["GERL101B1"]["requirement"])
