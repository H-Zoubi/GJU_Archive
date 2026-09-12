"""
Condense the fourteen resource types down to seven.

`choices` is not a database constraint, so the AlterField alone would leave
rows holding retired values like "past_paper" -- still stored, no longer in any
filter or label. The data migration is what actually moves them.
"""
from django.db import migrations, models

# Retired value -> its replacement. Everything not listed (slides, lab, book,
# video, other) keeps the name it already had.
RETIRED = {
    "past_paper": "exam",
    "midterm": "exam",
    "final": "exam",
    "quiz": "exam",
    "solution": "assignment",
    "project": "assignment",
    "lecture_notes": "notes",
    "summary": "notes",
}


def condense(apps, schema_editor):
    Resource = apps.get_model("resources", "Resource")
    for old, new in RETIRED.items():
        Resource.objects.filter(type=old).update(type=new)


def split(apps, schema_editor):
    """
    Reverse to the coarsest old value in each group.

    The merge is lossy -- once four exam types are one, nothing records which
    a given row used to be -- so reversing picks the general member of each
    group rather than pretending to restore the original.
    """
    Resource = apps.get_model("resources", "Resource")
    Resource.objects.filter(type="exam").update(type="past_paper")
    Resource.objects.filter(type="notes").update(type="lecture_notes")
    # "assignment" survives the merge unchanged, so it needs no reverse.


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0002_resource_upload_completed_at_download"),
    ]

    operations = [
        migrations.AlterField(
            model_name="resource",
            name="type",
            field=models.CharField(
                choices=[
                    ("slides", "Slides"),
                    ("exam", "Exams & quizzes"),
                    ("assignment", "Assignments & projects"),
                    ("notes", "Notes & summaries"),
                    ("lab", "Lab"),
                    ("book", "Book"),
                    ("video", "Video"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(condense, split),
    ]
