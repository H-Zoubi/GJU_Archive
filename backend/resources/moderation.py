"""
The moderation decisions themselves, in one place.

Approving is not just a status change: it stamps who decided and when, credits
the uploader (which is what eventually earns them auto-approval), and writes an
audit entry. Every one of those was previously missing from the admin action,
so uploaders' `approved_uploads_count` stayed at zero forever and nobody could
ever become a trusted uploader.

The admin action and the API both call these, so the two can never drift.
"""
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from moderation.models import AuditLog

from .models import Resource


def _log(actor, action: str, resource: Resource, **metadata) -> None:
    AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type="resources.Resource",
        target_id=str(resource.pk),
        metadata=metadata,
    )


@transaction.atomic
def approve(resource: Resource, actor) -> Resource:
    """Publish a resource. Idempotent: approving twice credits the uploader once."""
    if resource.status == Resource.Status.APPROVED:
        return resource

    resource.status = Resource.Status.APPROVED
    resource.approved_at = timezone.now()
    resource.approved_by = actor
    resource.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])

    if resource.uploader_id is not None:
        # F() rather than read-modify-write: two moderators clearing the queue
        # at once would otherwise each read the same count and one increment
        # would be lost.
        type(resource.uploader).objects.filter(pk=resource.uploader_id).update(
            approved_uploads_count=F("approved_uploads_count") + 1
        )

    _log(actor, "resource.approve", resource, title=resource.title)
    return resource


@transaction.atomic
def reject(resource: Resource, actor, reason: str = "") -> Resource:
    """
    Turn down an upload.

    The row stays so the uploader can see what happened and so the same file
    is not re-reviewed from scratch; `purge_files` deals with the object.
    """
    resource.status = Resource.Status.REJECTED
    resource.save(update_fields=["status", "updated_at"])
    _log(actor, "resource.reject", resource, title=resource.title, reason=reason)
    return resource


@transaction.atomic
def remove(resource: Resource, actor, reason: str = "") -> Resource:
    """
    Take down something already published.

    A soft delete, so a mistaken removal can be undone; the file survives the
    grace period in `purge_files` before the bytes go. If the resource had been
    approved, the uploader's credit is taken back with it -- otherwise removing
    spam would leave the spammer's path to auto-approval intact.
    """
    was_approved = resource.status == Resource.Status.APPROVED

    resource.status = Resource.Status.REMOVED
    resource.save(update_fields=["status", "updated_at"])
    resource.soft_delete()

    if was_approved and resource.uploader_id is not None:
        type(resource.uploader).objects.filter(
            pk=resource.uploader_id, approved_uploads_count__gt=0
        ).update(approved_uploads_count=F("approved_uploads_count") - 1)

    _log(actor, "resource.remove", resource, title=resource.title, reason=reason)
    return resource
