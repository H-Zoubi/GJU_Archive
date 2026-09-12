"""
Resource API.

The file itself never passes through Django. An upload is three calls --
`exists` (skip duplicates), `uploads/` (get a presigned PUT), `complete/`
(verify what landed in the bucket) -- and a download hands back a short-lived
presigned GET. Django's job is permission and bookkeeping, not bytes.
"""
from django.conf import settings
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from common import filetypes, storage

from .entitlements import check_download, check_upload
from .models import Download, Resource
from .serializers import LinkCreateSerializer, ResourceSerializer, UploadStartSerializer
from .uploads import verify_uploaded_file

# An entitlement denial maps to the status that tells the SPA what to do:
# 401 -> show the sign-in screen, 403 -> show why, 404 -> the file is gone.
_DENIAL_STATUS = {
    "login_required": status.HTTP_401_UNAUTHORIZED,
    "not_available": status.HTTP_404_NOT_FOUND,
}


def _denied(decision):
    return Response(
        {"detail": decision.detail, "code": decision.code},
        status=_DENIAL_STATUS.get(decision.code, status.HTTP_403_FORBIDDEN),
    )


class ResourceViewSet(viewsets.ReadOnlyModelViewSet):
    """Approved resources. Metadata is public; the bytes are gated."""

    serializer_class = ResourceSerializer
    permission_classes = [AllowAny]
    filter_backends = [SearchFilter]
    search_fields = ["title", "description", "course__code", "course__name"]

    def get_queryset(self):
        qs = (
            Resource.objects.alive()
            .filter(status=Resource.Status.APPROVED)
            .select_related("course", "term", "instructor", "uploader")
            .prefetch_related("tags")
            .annotate(download_count=Count("downloads", distinct=True))
            # Explicit: the Count above groups the query, which drops Django's
            # Meta.ordering and leaves pagination non-deterministic.
            .order_by("-created_at")
        )
        params = self.request.query_params
        course = params.get("course")
        if course:
            qs = qs.filter(course__code=course.upper())
        type_ = params.get("type")
        if type_:
            qs = qs.filter(type=type_)
        term = params.get("term")
        if term:
            qs = qs.filter(term_id=term)
        return qs

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        """Check entitlement, log the download, hand back a presigned GET."""
        resource = get_object_or_404(
            Resource.objects.alive().select_related("course"), pk=pk
        )
        decision = check_download(request.user, resource)
        if not decision:
            return _denied(decision)
        if resource.upload_completed_at is None:
            return Response(
                {"detail": "This file is still uploading.", "code": "not_available"},
                status=status.HTTP_404_NOT_FOUND,
            )

        Download.objects.create(user=request.user, resource=resource)
        url = storage.presign_get(
            resource.file_key,
            filename=resource.original_filename or resource.title,
            # Preview mode for PDF.js; otherwise force a save dialog.
            inline=request.query_params.get("inline") == "1",
        )
        return Response({"url": url, "expires_in": settings.S3_DOWNLOAD_URL_TTL})


class ResourceExistsView(APIView):
    """
    Duplicate check, called before the browser uploads anything.

    The client hashes the file locally and asks about the hash; if the archive
    already has it, the upload is skipped entirely and nothing crosses the
    network. Public, because knowing a file's hash already means holding it.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        sha256 = (request.query_params.get("sha256") or "").lower()
        if len(sha256) != 64:
            return Response(
                {"detail": "A 64-character hex sha256 is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        matches = (
            Resource.objects.alive()
            .filter(
                sha256=sha256,
                kind=Resource.Kind.FILE,
                # Only finished uploads count. Matching an abandoned row would
                # tell the client "we already have it" and leave the student
                # permanently unable to retry their own failed upload.
                upload_completed_at__isnull=False,
            )
            .exclude(status=Resource.Status.REJECTED)
            .select_related("course", "term", "instructor", "uploader")
        )
        course = request.query_params.get("course")
        in_course = matches.filter(course__code=course.upper()).exists() if course else False
        return Response(
            {
                "exists": matches.exists(),
                "in_this_course": in_course,
                "resources": ResourceSerializer(matches[:5], many=True).data,
            }
        )


class UploadStartView(APIView):
    """Step 2: reserve a pending Resource and return the presigned PUT URL."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "upload"

    def post(self, request):
        decision = check_upload(request.user)
        if not decision:
            return _denied(decision)

        serializer = UploadStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        file_type = filetypes.lookup(data["filename"])
        sha256 = data["sha256"].lower()

        # Every status, soft-deleted included: the course+sha256 uniqueness
        # constraint does not care why a row exists, so narrowing this lookup
        # would let a second row be built for a file that already has one and
        # fail with an IntegrityError at save time.
        existing = Resource.objects.filter(
            course=data["course"], sha256=sha256, kind=Resource.Kind.FILE
        ).first()

        if existing is not None and existing.upload_completed_at is not None:
            if existing.status == Resource.Status.REJECTED:
                refusal = "A moderator has already reviewed this file and turned it down."
            elif existing.is_deleted or existing.status == Resource.Status.REMOVED:
                refusal = "This file was taken down and cannot be re-uploaded."
            else:
                # Approved, or pending someone else's review: either way it is
                # accounted for and a second copy would just be noise.
                refusal = "This file is already in the archive for this course."
            return Response(
                {
                    "detail": refusal,
                    "code": "duplicate",
                    "resource": ResourceSerializer(existing).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        key = storage.build_key(sha256, data["filename"])
        # Reuse an abandoned row rather than tripping the course+sha256
        # uniqueness constraint when a student retries a failed upload.
        resource = existing or Resource(course=data["course"])
        resource.type = data["type"]
        resource.title = data["title"]
        resource.description = data.get("description", "")
        resource.term = data.get("term")
        resource.offering = data.get("offering")
        resource.instructor = data.get("instructor")
        resource.kind = Resource.Kind.FILE
        resource.file_key = key
        resource.sha256 = sha256
        resource.size_bytes = data["size_bytes"]
        resource.mime_type = file_type.mime
        resource.original_filename = data["filename"]
        resource.uploader = request.user
        resource.source = Resource.Source.UPLOAD
        resource.status = Resource.Status.PENDING
        resource.upload_completed_at = None
        # Only ever reached for a row whose file never arrived, so this is
        # reviving an abandoned attempt rather than resurrecting a takedown --
        # completed rows were refused above.
        resource.is_deleted = False
        resource.deleted_at = None
        resource.save()

        return Response(
            {
                "resource_id": resource.id,
                "upload_url": storage.presign_put(key, file_type.mime),
                "method": "PUT",
                "headers": {"Content-Type": file_type.mime},
                "expires_in": settings.S3_UPLOAD_URL_TTL,
            },
            status=status.HTTP_201_CREATED,
        )


class UploadCompleteView(APIView):
    """
    Step 3: confirm what actually landed in the bucket.

    Everything before this point is a claim by the client. Here the claim is
    checked against the object itself -- it exists, its size matches what was
    declared, and its first bytes really are the format the extension promised.
    A mismatch deletes the object rather than leaving it orphaned.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        resource = get_object_or_404(
            Resource.objects.alive(), pk=pk, kind=Resource.Kind.FILE
        )
        if resource.uploader_id != request.user.id and not request.user.is_staff:
            return Response(
                {"detail": "This is not your upload."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if resource.upload_completed_at is not None:
            return Response(ResourceSerializer(resource).data)

        error = verify_uploaded_file(resource)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        resource.upload_completed_at = timezone.now()
        # Students with a track record skip the queue; everyone else waits for
        # a moderator. Auto-approval is reversible from the admin.
        if request.user.is_trusted_uploader:
            resource.status = Resource.Status.APPROVED
            resource.approved_at = timezone.now()
        resource.save()
        return Response(ResourceSerializer(resource).data)


class LinkCreateView(APIView):
    """Videos and Drive folders are recorded as links; we never rehost them."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "upload"

    def post(self, request):
        decision = check_upload(request.user)
        if not decision:
            return _denied(decision)
        serializer = LinkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = serializer.save(
            kind=Resource.Kind.LINK,
            uploader=request.user,
            source=Resource.Source.UPLOAD,
            status=Resource.Status.PENDING,
        )
        return Response(ResourceSerializer(resource).data, status=status.HTTP_201_CREATED)


class MyUploadsView(APIView):
    """A student's own uploads, including ones still awaiting moderation."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Resource.objects.alive()
            .filter(uploader=request.user)
            .select_related("course", "term", "instructor", "uploader")
            .annotate(download_count=Count("downloads", distinct=True))
            .order_by("-created_at")
        )
        return Response(ResourceSerializer(qs, many=True).data)
