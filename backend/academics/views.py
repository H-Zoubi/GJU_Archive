from django.db.models import Count
from rest_framework import viewsets
from rest_framework.filters import SearchFilter

from .models import Course, Instructor, Major, Term
from .serializers import (
    CourseDetailSerializer,
    CourseListSerializer,
    InstructorDetailSerializer,
    InstructorSerializer,
    MajorSerializer,
    TermSerializer,
)

# Catalog is public (read-only). The global IsAuthenticatedOrReadOnly default
# already allows anonymous GETs, so no extra permission classes are needed.


class MajorViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MajorSerializer
    lookup_field = "slug"
    filter_backends = [SearchFilter]
    search_fields = ["name", "code"]

    def get_queryset(self):
        return (
            Major.objects.filter(is_active=True)
            .annotate(course_count=Count("courses"))
            .order_by("name")
        )


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "code"
    filter_backends = [SearchFilter]
    search_fields = ["code", "display_code", "name"]

    def get_serializer_class(self):
        return CourseListSerializer if self.action == "list" else CourseDetailSerializer

    def get_queryset(self):
        qs = Course.objects.all().order_by("code")
        major = self.request.query_params.get("major")
        if major:
            qs = qs.filter(majors__slug=major)
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                "majors", "prerequisites", "offerings__term", "offerings__instructors"
            )
        return qs.distinct()


class InstructorViewSet(viewsets.ReadOnlyModelViewSet):
    filter_backends = [SearchFilter]
    search_fields = ["full_name"]

    def get_serializer_class(self):
        return InstructorSerializer if self.action == "list" else InstructorDetailSerializer

    def get_queryset(self):
        qs = Instructor.objects.filter(is_active=True).order_by("full_name")
        if self.action == "retrieve":
            qs = qs.prefetch_related("offerings__term", "offerings__course")
        return qs


class TermViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
