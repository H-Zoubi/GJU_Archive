"""Resources API routes."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    LinkCreateView,
    MyUploadsView,
    ResourceExistsView,
    ResourceViewSet,
    UploadCompleteView,
    UploadStartView,
)
from .views_moderation import (
    ModerationActionView,
    ModerationBulkView,
    ModerationPreviewView,
    ModerationQueueView,
)

router = DefaultRouter()
router.register("resources", ResourceViewSet, basename="resource")

urlpatterns = [
    # Declared before the router so "exists" is not swallowed by the
    # resources/<pk>/ detail route.
    path("resources/exists/", ResourceExistsView.as_view(), name="resource-exists"),
    path("uploads/", UploadStartView.as_view(), name="upload-start"),
    path("uploads/<int:pk>/complete/", UploadCompleteView.as_view(), name="upload-complete"),
    path("uploads/mine/", MyUploadsView.as_view(), name="upload-mine"),
    path("links/", LinkCreateView.as_view(), name="link-create"),
    path("moderation/queue/", ModerationQueueView.as_view(), name="moderation-queue"),
    path("moderation/bulk/", ModerationBulkView.as_view(), name="moderation-bulk"),
    path(
        "moderation/<int:pk>/preview/",
        ModerationPreviewView.as_view(),
        name="moderation-preview",
    ),
    path(
        "moderation/<int:pk>/<str:action>/",
        ModerationActionView.as_view(),
        name="moderation-action",
    ),
    *router.urls,
]
