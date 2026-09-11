from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import StudentProfile, User

# GjuCredential is intentionally NOT registered in the admin: the encrypted
# GJU password must never be viewable through any interface.


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "full_name", "role", "is_gju_verified", "is_banned", "is_staff"]
    list_filter = ["role", "is_gju_verified", "is_banned", "is_staff", "is_active"]
    search_fields = ["email", "full_name"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "role", "instructor")}),
        ("Status", {"fields": ("is_email_verified", "is_gju_verified", "is_banned", "approved_uploads_count")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ["date_joined", "last_login"]
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "role"),
        }),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "major", "entry_year", "expected_grad_year"]
    search_fields = ["user__email"]
