from rest_framework import serializers

from .models import Course, CourseOffering, Instructor, Major, Term


class MajorSerializer(serializers.ModelSerializer):
    degree_level_display = serializers.CharField(
        source="get_degree_level_display", read_only=True
    )
    course_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Major
        fields = [
            "id",
            "code",
            "name",
            "degree_level",
            "degree_level_display",
            "partner_institution",
            "slug",
            "course_count",
        ]


class TermSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = Term
        fields = ["id", "season", "year", "is_current", "label"]


class InstructorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instructor
        fields = ["id", "full_name", "title", "email", "is_active"]


class CourseListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "code", "display_code", "name", "credit_hours", "slug"]


class OfferingSerializer(serializers.ModelSerializer):
    """A section: used to render a course's / instructor's semester history."""

    term = TermSerializer(read_only=True)
    instructors = InstructorSerializer(many=True, read_only=True)
    course_code = serializers.CharField(source="course.display_code", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)

    class Meta:
        model = CourseOffering
        fields = [
            "id",
            "course_code",
            "course_name",
            "term",
            "section_number",
            "campus",
            "language",
            "instructors",
        ]


class CourseDetailSerializer(serializers.ModelSerializer):
    majors = MajorSerializer(many=True, read_only=True)
    prerequisites = CourseListSerializer(many=True, read_only=True)
    offerings = OfferingSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "code",
            "display_code",
            "name",
            "description",
            "credit_hours",
            "level",
            "slug",
            "majors",
            "prerequisites",
            "offerings",
        ]


class InstructorDetailSerializer(serializers.ModelSerializer):
    """Instructor plus their course history (all offerings they taught)."""

    offerings = OfferingSerializer(many=True, read_only=True)

    class Meta:
        model = Instructor
        fields = ["id", "full_name", "title", "email", "is_active", "offerings"]
