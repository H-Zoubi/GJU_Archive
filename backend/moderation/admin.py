from django.contrib import admin

from .models import AuditLog, Report, TakedownRequest


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["reason", "resource", "status", "reporter", "created_at"]
    list_filter = ["status", "reason"]
    search_fields = ["resource__title"]
    autocomplete_fields = ["resource", "reporter", "handled_by"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "actor", "target_type", "target_id", "created_at"]
    list_filter = ["action"]
    search_fields = ["action", "target_id"]
    readonly_fields = ["actor", "action", "target_type", "target_id", "metadata", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TakedownRequest)
class TakedownRequestAdmin(admin.ModelAdmin):
    list_display = ["requester_email", "resource", "status", "created_at"]
    list_filter = ["status"]
