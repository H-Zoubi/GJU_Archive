from django.contrib import admin

from .models import ImportRun, MoodleCourseMap


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ["user", "status", "courses_seen", "files_added", "started_at"]
    list_filter = ["status"]
    readonly_fields = ["started_at", "finished_at"]


@admin.register(MoodleCourseMap)
class MoodleCourseMapAdmin(admin.ModelAdmin):
    list_display = ["moodle_course_id", "course", "offering", "confidence"]
    list_filter = ["confidence"]
    search_fields = ["moodle_shortname", "moodle_fullname"]
