from django.contrib import admin
from django.utils import timezone

from .models import Resource, Tag, Vote


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ["title", "course", "type", "status", "source", "uploader", "created_at"]
    list_filter = ["status", "type", "source", "kind", "visibility"]
    search_fields = ["title", "course__code", "course__name"]
    autocomplete_fields = ["course", "offering", "instructor", "uploader"]
    readonly_fields = ["sha256", "size_bytes", "mime_type", "created_at", "updated_at"]
    actions = ["approve", "reject", "remove"]

    @admin.action(description="Approve selected resources")
    def approve(self, request, queryset):
        queryset.update(status=Resource.Status.APPROVED, approved_at=timezone.now(), approved_by=request.user)

    @admin.action(description="Reject selected resources")
    def reject(self, request, queryset):
        queryset.update(status=Resource.Status.REJECTED)

    @admin.action(description="Remove selected resources (soft delete)")
    def remove(self, request, queryset):
        for resource in queryset:
            resource.status = Resource.Status.REMOVED
            resource.soft_delete()


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ["user", "resource", "value"]
