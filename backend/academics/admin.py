from django.contrib import admin

from .models import (
    Course,
    CourseOffering,
    ExamSchedule,
    Instructor,
    Major,
    MeetingTime,
    Subject,
    SubjectPrefix,
    Term,
)


class SubjectPrefixInline(admin.TabularInline):
    model = SubjectPrefix
    extra = 0
    filter_horizontal = ["majors"]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    """The prefix -> subject grouping is editable here, no deploy needed."""

    list_display = ["name", "is_university_wide", "sort_order", "prefix_list"]
    list_filter = ["is_university_wide"]
    list_editable = ["sort_order"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SubjectPrefixInline]

    @admin.display(description="Prefixes")
    def prefix_list(self, obj):
        return ", ".join(p.prefix for p in obj.prefixes.all())


@admin.register(SubjectPrefix)
class SubjectPrefixAdmin(admin.ModelAdmin):
    list_display = ["prefix", "subject"]
    list_filter = ["subject"]
    search_fields = ["prefix"]
    filter_horizontal = ["majors"]


@admin.register(Major)
class MajorAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "degree_level", "is_active"]
    list_filter = ["degree_level", "is_active"]
    search_fields = ["name", "code"]
    prepopulated_fields = {"slug": ("code", "name")}


@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display = ["full_name", "title", "email", "is_active"]
    search_fields = ["full_name", "email"]
    list_filter = ["is_active"]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["display_code", "name", "credit_hours", "level"]
    search_fields = ["code", "display_code", "name"]
    filter_horizontal = ["majors", "prerequisites", "corequisites"]


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ["__str__", "season", "year", "is_current"]
    list_filter = ["season", "is_current"]


class MeetingTimeInline(admin.TabularInline):
    model = MeetingTime
    extra = 0


class ExamScheduleInline(admin.TabularInline):
    model = ExamSchedule
    extra = 0


@admin.register(CourseOffering)
class CourseOfferingAdmin(admin.ModelAdmin):
    list_display = ["course", "term", "section_number", "moodle_course_id"]
    list_filter = ["term", "language", "campus"]
    search_fields = ["course__code", "course__name"]
    filter_horizontal = ["instructors"]
    inlines = [MeetingTimeInline, ExamScheduleInline]
