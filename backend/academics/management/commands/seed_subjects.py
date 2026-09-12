"""
Seed the subject grouping and attach every course to a subject and its majors.

Browsing by major alone does not work at GJU: German, English, Arabic, Maths,
Physics, National Education and Sports are taken by everyone, so they belong to
no single major. Browsing by course-code prefix does work, because the prefix is
already in the data and nobody has to maintain it.

Raw prefixes are still too granular (64 of them, 13 with a single course) and
they split subjects that are plainly one thing, because GJU renumbered courses
over the years. So several prefixes map to one subject:

    ME + MECH + TME                        -> Mechanical Engineering
    ARC + ARCH + IARC                      -> Architecture
    GERL + GERS + GLS + GEBC + MADAF + DAF -> German
    CE + ECE                               -> Computer / Electrical Engineering

The mapping lives in the database (Subject, SubjectPrefix), so it can be fixed
from the admin later without a code change.

    python manage.py seed_subjects
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from academics.models import Course, Major, Subject, SubjectPrefix, code_prefix

# name, university_wide, [prefixes], [major codes]
SUBJECTS = [
    ("Computer Science", False, ["CS"], ["CS"]),
    ("Computer Engineering", False, ["CE", "ECE"], ["CE"]),
    ("Game Design and Media Informatics", False, ["DMI"], ["GDMI"]),
    ("Industrial Engineering", False, ["IE"], ["IE"]),
    # AME and ENRE are single legacy courses from an older numbering scheme.
    ("Mechanical Engineering", False,
     ["ME", "MECH", "TME", "HT", "AME", "ENRE"], ["MME", "MTE"]),
    ("Civil Engineering", False, ["CEE", "CVE"], ["SISE"]),
    ("Energy and Electrical Engineering", False, ["ENE", "EE", "ERE"], ["EE", "ENE"]),
    ("Biomedical Engineering", False, ["BM", "BIO"], ["BME"]),
    ("Pharmaceutical and Chemical Engineering", False, ["PCE", "CHEM"], ["PCE"]),
    ("Architecture", False, ["ARC", "ARCH", "IARC", "AC", "SABE", "SP", "GB"],
     ["ARCH", "INAR"]),
    ("Design and Visual Communication", False, ["DES"], ["DVC"]),
    ("Accounting", False, ["ACC"], ["IA"]),
    ("Logistics", False, ["LOGS"], ["LS"]),
    ("Management", False, ["MGT", "MBA"], ["MGTS"]),
    ("Business Intelligence and Data Analytics", False, ["BIDA"], ["BIDA"]),
    ("Digital Marketing", False, ["DM"], ["DMKT"]),
    ("Entrepreneurship and Innovation", False, ["EIM", "BE", "SE"], []),
    ("Nursing", False, ["NUR"], ["NUR"]),
    ("Social Work", False, ["SW"], []),
    ("Translation", False, ["TRA"], ["TRANS"]),
    # Taken across majors.
    # Everyone takes German at GJU, so the subject belongs to no major:
    # attaching it wholesale made Translation look like a 107-course major.
    # The GEBC prefix is the exception — those courses are that major's own.
    ("German", True, ["GERL", "GERS", "GLS", "MADAF", "DAF"], []),
    ("German for Business and Communication", False, ["GEBC"], ["GEBC"]),
    ("English", True, ["ENGL", "SL"], []),
    ("Arabic", True, ["ARB", "AFL"], []),
    ("Mathematics", True, ["MATH"], []),
    ("Physics", True, ["PHYS"], []),
    ("University Requirements", True,
     ["UE", "NE", "NEE", "EI", "SFTS", "MILS", "IC", "PE"], []),
    ("Training and Exchange", True, ["DS", "BSC", "GJUHTU", "HWASH"], []),
]


class Command(BaseCommand):
    help = "Seed subjects and attach courses to subjects and majors."

    @transaction.atomic
    def handle(self, *args, **options):
        majors = {m.code: m for m in Major.objects.all()}
        prefix_to_subject = {}
        prefix_to_majors = {}

        for order, (name, wide, prefixes, major_codes) in enumerate(SUBJECTS):
            subject, _ = Subject.objects.update_or_create(
                name=name,
                defaults={"is_university_wide": wide, "sort_order": order},
            )
            linked = [majors[c] for c in major_codes if c in majors]
            for prefix in prefixes:
                entry, _ = SubjectPrefix.objects.update_or_create(
                    prefix=prefix, defaults={"subject": subject}
                )
                entry.majors.set(linked)
                prefix_to_subject[prefix] = subject
                prefix_to_majors[prefix] = linked

        self.stdout.write(
            f"Subjects {Subject.objects.count()}, "
            f"prefixes {SubjectPrefix.objects.count()}"
        )

        # Attach every course, backfilling code_prefix for rows imported before
        # the field existed.
        attached = unmatched = 0
        missing = {}
        for course in Course.objects.all():
            prefix = course.code_prefix or code_prefix(course.code)
            subject = prefix_to_subject.get(prefix)
            Course.objects.filter(pk=course.pk).update(
                code_prefix=prefix, subject=subject
            )
            if subject:
                course.majors.set(prefix_to_majors.get(prefix, []))
                attached += 1
            else:
                unmatched += 1
                missing[prefix] = missing.get(prefix, 0) + 1

        self.stdout.write(
            self.style.SUCCESS(f"Attached {attached} courses to a subject.")
        )
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"{unmatched} courses have no subject: "
                    + ", ".join(f"{p}({n})" for p, n in sorted(missing.items()))
                )
            )
