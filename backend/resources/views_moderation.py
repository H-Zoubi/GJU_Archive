"""
Moderation API behind the in-app review dashboard.

The Django admin can do all of this, but not quickly: reviewing an upload there
means a list page, a detail page, and no way to actually look at the file. This
exists so clearing the queue is preview-approve-next.
"""
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from common import storage

from . import moderation
from .models import Resource
from .serializers import ModerationResourceSerializer

ACTIONS = {
    "approve": moderation.approve,
    "reject": moderation.reject,
    "remove": moderation.remove,
}


class CanModerate(BasePermission):
    """Moderators and above; see User.can_moderate for who that is."""

    message = "You do not have moderator access."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.can_moderate)


def _queue():
    return (
        Resource.objects.alive()
        .filter(status=Resource.Status.PENDING)
        # Nothing half-uploaded: a reserved row whose file never arrived is not
        # a submission and must not sit in a human's queue.
        .exclude(kind=Resource.Kind.FILE, upload_completed_at__isnull=True)
        .select_related("course", "term", "instructor", "uploader")
        .annotate(download_count=Count("downloads", distinct=True))
        .order_by("created_at")  # oldest first: nothing waits forever
    )


class ModerationQueueView(APIView):
    """Everything waiting for a decision, oldest first."""

    permission_classes = [CanModerate]

    def get(self, request):
        queue = _queue()
        return Response(
            {
                "count": queue.count(),
                "results": ModerationResourceSerializer(queue[:100], many=True).data,
            }
        )


class ModerationActionView(APIView):
    """Apply one decision to one resource."""

    permission_classes = [CanModerate]

    def post(self, request, pk, action):
        handler = ACTIONS.get(action)
        if handler is None:
            return Response(
                {"detail": f"Unknown action {action!r}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        resource = get_object_or_404(Resource.objects.all(), pk=pk)
        reason = str(request.data.get("reason", ""))[:500]

        if action == "approve":
            handler(resource, request.user)
        else:
            handler(resource, request.user, reason=reason)

        resource.refresh_from_db()
        return Response(ModerationResourceSerializer(resource).data)


class ModerationBulkView(APIView):
    """Apply one decision to many resources -- the 'approve all' button."""

    permission_classes = [CanModerate]

    def post(self, request):
        action = request.data.get("action")
        handler = ACTIONS.get(action)
        if handler is None:
            return Response(
                {"detail": f"Unknown action {action!r}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ids = request.data.get("ids") or []
        if not isinstance(ids, list):
            return Response(
                {"detail": "ids must be a list."}, status=status.HTTP_400_BAD_REQUEST
            )

        reason = str(request.data.get("reason", ""))[:500]
        done = []
        for resource in Resource.objects.filter(pk__in=ids[:100]):
            if action == "approve":
                handler(resource, request.user)
            else:
                handler(resource, request.user, reason=reason)
            done.append(resource.pk)
        return Response({"action": action, "applied": done})


class ModerationPreviewView(APIView):
    """
    A presigned URL for a file that is not public yet.

    Separate from the student download endpoint on purpose: that one refuses
    anything not approved, which is exactly the thing a moderator needs to
    look at. No Download row is written -- reviewing is not reading.
    """

    permission_classes = [CanModerate]

    def get(self, request, pk):
        resource = get_object_or_404(
            Resource.objects.all(), pk=pk, kind=Resource.Kind.FILE
        )
        if resource.upload_completed_at is None or not resource.file_key:
            return Response(
                {"detail": "This upload never finished."},
                status=status.HTTP_404_NOT_FOUND,
            )
        url = storage.presign_get(
            resource.file_key,
            filename=resource.original_filename or resource.title,
            inline=True,
        )
        return Response({"url": url})
