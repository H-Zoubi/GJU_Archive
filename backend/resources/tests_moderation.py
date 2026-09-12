"""
Tests for the moderation service layer and the review-dashboard API.

resources/tests.py covers the upload/download flow; this covers the decision
logic in moderation.py (crediting, idempotency, audit trail) and the API that
sits on top of it (permissions, queue contents, bulk actions, preview).
"""
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from academics.models import Course
from common import storage
from moderation.models import AuditLog

from . import moderation
from .models import Resource

User = get_user_model()

SHA = "a" * 64


def _make_resource(course, uploader=None, **overrides):
    fields = {
        "course": course,
        "type": "exam",
        "title": "Midterm 2023",
        "kind": Resource.Kind.FILE,
        "file_key": storage.build_key(SHA, "midterm.pdf"),
        "sha256": SHA,
        "size_bytes": 1024,
        "status": Resource.Status.PENDING,
        "uploader": uploader,
        "upload_completed_at": datetime(2026, 1, 1, tzinfo=dt_timezone.utc),
    }
    fields.update(overrides)
    return Resource.objects.create(**fields)


class ModerationServiceTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(code="CS116", name="Programming")
        self.moderator = User.objects.create_user(
            email="mod@gju.edu.jo", password="pw-for-tests-1234"
        )
        self.uploader = User.objects.create_user(
            email="student@gju.edu.jo", password="pw-for-tests-1234"
        )

    def test_approve_stamps_the_decision_and_credits_the_uploader(self):
        resource = _make_resource(self.course, uploader=self.uploader)
        moderation.approve(resource, self.moderator)

        resource.refresh_from_db()
        self.assertEqual(resource.status, Resource.Status.APPROVED)
        self.assertEqual(resource.approved_by, self.moderator)
        self.assertIsNotNone(resource.approved_at)

        self.uploader.refresh_from_db()
        self.assertEqual(self.uploader.approved_uploads_count, 1)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "resource.approve")
        self.assertEqual(entry.actor, self.moderator)
        self.assertEqual(entry.target_id, str(resource.pk))

    def test_approving_twice_credits_the_uploader_only_once(self):
        resource = _make_resource(self.course, uploader=self.uploader)
        moderation.approve(resource, self.moderator)
        moderation.approve(resource, self.moderator)

        self.uploader.refresh_from_db()
        self.assertEqual(self.uploader.approved_uploads_count, 1)
        self.assertEqual(AuditLog.objects.filter(action="resource.approve").count(), 1)

    def test_reject_leaves_the_row_and_logs_the_reason(self):
        resource = _make_resource(self.course, uploader=self.uploader)
        moderation.reject(resource, self.moderator, reason="wrong course")

        resource.refresh_from_db()
        self.assertEqual(resource.status, Resource.Status.REJECTED)
        self.assertTrue(Resource.objects.filter(pk=resource.pk).exists())

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "resource.reject")
        self.assertEqual(entry.metadata["reason"], "wrong course")

    def test_removing_an_approved_resource_soft_deletes_and_takes_back_credit(self):
        resource = _make_resource(
            self.course,
            uploader=self.uploader,
            status=Resource.Status.APPROVED,
        )
        self.uploader.approved_uploads_count = 1
        self.uploader.save()

        moderation.remove(resource, self.moderator, reason="copyright")

        resource.refresh_from_db()
        self.assertEqual(resource.status, Resource.Status.REMOVED)
        self.assertTrue(resource.is_deleted)

        self.uploader.refresh_from_db()
        self.assertEqual(self.uploader.approved_uploads_count, 0)

    def test_removing_a_pending_resource_does_not_touch_uploader_credit(self):
        resource = _make_resource(self.course, uploader=self.uploader)
        moderation.remove(resource, self.moderator)

        self.uploader.refresh_from_db()
        self.assertEqual(self.uploader.approved_uploads_count, 0)

    def test_uploader_credit_never_goes_negative(self):
        resource = _make_resource(
            self.course,
            uploader=self.uploader,
            status=Resource.Status.APPROVED,
        )
        moderation.remove(resource, self.moderator)

        self.uploader.refresh_from_db()
        self.assertEqual(self.uploader.approved_uploads_count, 0)


class ModerationApiTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(code="CS116", name="Programming")
        self.moderator = User.objects.create_user(
            email="mod@gju.edu.jo", password="pw-for-tests-1234", role="moderator"
        )
        self.student = User.objects.create_user(
            email="student@gju.edu.jo", password="pw-for-tests-1234"
        )

    def test_student_is_refused_the_queue(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("moderation-queue"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_is_refused_the_queue(self):
        response = self.client.get(reverse("moderation-queue"))
        self.assertIn(response.status_code, (401, 403))

    def test_queue_lists_pending_oldest_first_and_skips_unfinished_uploads(self):
        older = _make_resource(self.course, uploader=self.student, title="Older")
        older.created_at = datetime(2020, 1, 1, tzinfo=dt_timezone.utc)
        older.save(update_fields=["created_at"])
        _make_resource(self.course, uploader=self.student, title="Newer")
        _make_resource(
            self.course,
            uploader=self.student,
            title="Unfinished",
            upload_completed_at=None,
        )

        self.client.force_login(self.moderator)
        response = self.client.get(reverse("moderation-queue"))
        self.assertEqual(response.status_code, 200)
        titles = [row["title"] for row in response.json()["results"]]
        self.assertEqual(titles, ["Older", "Newer"])

    def test_queue_excludes_already_decided_resources(self):
        _make_resource(
            self.course, uploader=self.student, status=Resource.Status.APPROVED
        )
        self.client.force_login(self.moderator)
        response = self.client.get(reverse("moderation-queue"))
        self.assertEqual(response.json()["count"], 0)

    def test_approve_action_publishes_the_resource(self):
        resource = _make_resource(self.course, uploader=self.student)
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("moderation-action", args=[resource.pk, "approve"]),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "approved")

    def test_unknown_action_is_rejected(self):
        resource = _make_resource(self.course, uploader=self.student)
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("moderation-action", args=[resource.pk, "delete"]),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_approve_applies_to_every_id(self):
        a = _make_resource(self.course, uploader=self.student, title="A")
        b = _make_resource(self.course, uploader=self.student, title="B")
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("moderation-bulk"),
            {"action": "approve", "ids": [a.pk, b.pk]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(response.json()["applied"], [a.pk, b.pk])
        self.assertEqual(
            Resource.objects.filter(status=Resource.Status.APPROVED).count(), 2
        )

    def test_preview_refuses_an_unfinished_upload(self):
        resource = _make_resource(
            self.course, uploader=self.student, upload_completed_at=None
        )
        self.client.force_login(self.moderator)
        response = self.client.get(reverse("moderation-preview", args=[resource.pk]))
        self.assertEqual(response.status_code, 404)

    def test_preview_signs_a_url_for_a_finished_upload(self):
        resource = _make_resource(self.course, uploader=self.student)
        self.client.force_login(self.moderator)
        from unittest import mock

        with mock.patch.object(storage, "presign_get", return_value="https://bucket/get"):
            response = self.client.get(reverse("moderation-preview", args=[resource.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], "https://bucket/get")

    def test_superuser_can_moderate_even_without_the_role(self):
        superuser = User.objects.create_superuser(
            email="root@gju.edu.jo", password="pw-for-tests-1234"
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse("moderation-queue"))
        self.assertEqual(response.status_code, 200)
