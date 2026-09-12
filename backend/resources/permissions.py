from rest_framework.permissions import BasePermission


class IsImportBot(BasePermission):
    """
    A service account authenticated by a bot token, not a student session.

    Gates the ingest API: only an importer job running as its own process
    (Telegram export, later the Moodle worker) should reach it, never a
    student session even if somehow token-authenticated.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_service_account)
