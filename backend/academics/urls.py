"""Academics API routes."""
from rest_framework.routers import DefaultRouter

from .views import CourseViewSet, InstructorViewSet, MajorViewSet, TermViewSet

router = DefaultRouter()
router.register("majors", MajorViewSet, basename="major")
router.register("courses", CourseViewSet, basename="course")
router.register("instructors", InstructorViewSet, basename="instructor")
router.register("terms", TermViewSet, basename="term")

urlpatterns = router.urls
