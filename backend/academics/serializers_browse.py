"""Serializers for the browse UI: subjects, and courses filtered by them."""
from rest_framework import serializers

from .models import Subject


class SubjectSerializer(serializers.ModelSerializer):
    course_count = serializers.IntegerField(read_only=True)
    prefixes = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "slug",
            "is_university_wide",
            "course_count",
            "prefixes",
        ]

    def get_prefixes(self, obj):
        """Shown in the UI so 'Mechanical Engineering' reads as ME/MECH/TME."""
        return [p.prefix for p in obj.prefixes.all()]
