"""Resource read/write serializers. `file_key` is never exposed."""
from rest_framework import serializers

from academics.models import Course, CourseOffering, Instructor, Term
from common import filetypes

from .models import Resource, ResourceType, Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "slug"]


class ResourceSerializer(serializers.ModelSerializer):
    """
    Public shape of a resource.

    Metadata is public (it is what search engines and undecided students see);
    the bytes are not. Nothing here reveals the object key, so the only way to
    reach a file is the download endpoint, which runs the entitlement check.
    """

    course_code = serializers.CharField(source="course.code", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)
    # Not source="term.__str__": on a resource with no term that resolves to
    # NoneType's bound __str__ method rather than raising, and the field
    # happily renders that object's repr into the API response.
    term_label = serializers.SerializerMethodField()
    instructor_name = serializers.CharField(
        source="instructor.full_name", read_only=True, default=None
    )
    uploader_name = serializers.SerializerMethodField()
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    download_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Resource
        fields = [
            "id",
            "title",
            "description",
            "type",
            "type_label",
            "kind",
            "course_code",
            "course_name",
            "term_label",
            "instructor_name",
            "uploader_name",
            "tags",
            "url",
            "size_bytes",
            "mime_type",
            "original_filename",
            "source",
            "status",
            "download_count",
            "created_at",
        ]
        read_only_fields = fields

    def get_term_label(self, obj) -> str | None:
        return str(obj.term) if obj.term_id else None

    def get_uploader_name(self, obj) -> str:
        # Uploads are credited by display name only; the email stays private.
        if obj.uploader_id is None:
            return "GJU Archive"
        return obj.uploader.full_name or obj.uploader.email.split("@")[0]


class UploadStartSerializer(serializers.Serializer):
    """
    Step 1 of an upload: everything Django needs to mint a presigned PUT.

    The file itself is not here — the browser sends it straight to the bucket.
    The hash is computed client-side so a duplicate can be caught before a
    single byte crosses the network.
    """

    course = serializers.SlugRelatedField(slug_field="code", queryset=Course.objects.all())
    type = serializers.ChoiceField(choices=ResourceType.choices)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    term = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(), required=False, allow_null=True
    )
    offering = serializers.PrimaryKeyRelatedField(
        queryset=CourseOffering.objects.all(), required=False, allow_null=True
    )
    instructor = serializers.PrimaryKeyRelatedField(
        queryset=Instructor.objects.all(), required=False, allow_null=True
    )
    filename = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField(min_value=1)
    sha256 = serializers.RegexField(r"^[0-9a-f]{64}$", help_text="Lowercase hex SHA-256.")

    def validate_filename(self, value):
        if filetypes.lookup(value) is None:
            allowed = ", ".join(filetypes.ALLOWED_EXTENSIONS)
            raise serializers.ValidationError(f"Unsupported file type. Allowed: {allowed}.")
        return value

    def validate_size_bytes(self, value):
        from django.conf import settings

        if value > settings.MAX_UPLOAD_BYTES:
            limit_mb = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"Files must be {limit_mb} MB or smaller.")
        return value


class IngestUploadStartSerializer(UploadStartSerializer):
    """
    Step 1 of an ingest upload — same shape as a student's, plus which
    importer job this came from. There is no `offering`: an importer knows a
    course and (loosely) a term, not a specific section.
    """

    offering = None
    source = serializers.ChoiceField(
        choices=[Resource.Source.TELEGRAM_IMPORT, Resource.Source.AUTO_IMPORT]
    )


class LinkCreateSerializer(serializers.ModelSerializer):
    """Videos and external drives are stored as links, never rehosted."""

    course = serializers.SlugRelatedField(slug_field="code", queryset=Course.objects.all())

    class Meta:
        model = Resource
        fields = [
            "course",
            "type",
            "title",
            "description",
            "term",
            "offering",
            "instructor",
            "url",
        ]

    def validate_url(self, value):
        if not value:
            raise serializers.ValidationError("A link is required.")
        return value


class ModerationResourceSerializer(ResourceSerializer):
    """
    The reviewer's view, which is allowed to show more than the public one.

    Deciding on an upload needs the things a student is not shown: who
    submitted it (spam is a pattern across a person's uploads, not a property
    of one file), and the filename they chose, which is often the clearest
    signal that something is mislabelled.
    """

    uploader_email = serializers.EmailField(
        source="uploader.email", read_only=True, default=None
    )
    uploader_approved_count = serializers.IntegerField(
        source="uploader.approved_uploads_count", read_only=True, default=0
    )

    class Meta(ResourceSerializer.Meta):
        fields = ResourceSerializer.Meta.fields + [
            "uploader_email",
            "uploader_approved_count",
            "upload_completed_at",
        ]
        read_only_fields = fields
