from django.contrib import admin

from .models import (
    Course,
    CourseOffering,
    ExamSchedule,
    Instructor,
    Major,
    MeetingTime,
    Term,
)


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
