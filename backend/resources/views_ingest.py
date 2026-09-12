"""
Ingest API for importer jobs — the Telegram export importer today, the
Moodle auto-import worker later — that run as their own OS processes with no
Django settings or database access of their own.

They authenticate with a bot token (see `accounts.create_import_bot`) and
speak the same presigned-upload protocol a student's browser does: start,
PUT the bytes to the bucket, complete. That keeps there being exactly one
upload pipeline and one integrity check (`resources.uploads.verify_uploaded_file`)
rather than a second one that quietly drifts from the first. The only real
difference is that an ingest row is auto-approved on completion: `source`
records where it actually came from, and nobody re-reviews content that was
already shared and read once.
"""
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common import filetypes, storage

from .models import Resource
from .permissions import IsImportBot
from .serializers import IngestUploadStartSerializer, ResourceSerializer
from .uploads import verify_uploaded_file

_INGEST_SOURCES = (Resource.Source.TELEGRAM_IMPORT, Resource.Source.AUTO_IMPORT)


class IngestUploadStartView(APIView):
    """Ingest step 1: reserve a Resource and return a presigned PUT."""

    permission_classes = [IsImportBot]

    def post(self, request):
        serializer = IngestUploadStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        file_type = filetypes.lookup(data["filename"])
        sha256 = data["sha256"].lower()

        existing = Resource.objects.filter(
            course=data["course"], sha256=sha256, kind=Resource.Kind.FILE
        ).first()
        if existing is not None and existing.upload_completed_at is not None:
            return Response(
                {
                    "detail": "This file is already in the archive for this course.",
                    "code": "duplicate",
                    "resource": ResourceSerializer(existing).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        key = storage.build_key(sha256, data["filename"])
        # Reuse an abandoned row rather than tripping the course+sha256
        # uniqueness constraint, same as a student's retried upload.
        resource = existing or Resource(course=data["course"])
        resource.type = data["type"]
        resource.title = data["title"]
        resource.description = data.get("description", "")
        resource.term = data.get("term")
        resource.instructor = data.get("instructor")
        resource.kind = Resource.Kind.FILE
        resource.file_key = key
        resource.sha256 = sha256
        resource.size_bytes = data["size_bytes"]
        resource.mime_type = file_type.mime
        resource.original_filename = data["filename"]
        resource.uploader = None
        resource.source = data["source"]
        resource.status = Resource.Status.PENDING
        resource.upload_completed_at = None
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


class IngestUploadCompleteView(APIView):
    """Ingest step 2: verify what landed in the bucket, then auto-approve."""

    permission_classes = [IsImportBot]

    def post(self, request, pk):
        resource = get_object_or_404(
            Resource.objects.alive(),
            pk=pk,
            kind=Resource.Kind.FILE,
            source__in=_INGEST_SOURCES,
        )
        if resource.upload_completed_at is not None:
            return Response(ResourceSerializer(resource).data)

        error = verify_uploaded_file(resource)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        resource.upload_completed_at = timezone.now()
        resource.status = Resource.Status.APPROVED
        resource.approved_at = timezone.now()
        resource.save()
        return Response(ResourceSerializer(resource).data)
