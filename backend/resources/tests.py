"""
Tests for the file layer.

The bucket is mocked: these cover Django's half of the contract -- which
requests are allowed, what gets written to the database, and what happens when
the object that lands in storage does not match what the client declared. The
S3 calls themselves are boto3's to get right.
"""
import hashlib
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from academics.models import Course
from common import filetypes, storage

from .models import Download, Resource

User = get_user_model()

PDF_BYTES = b"%PDF-1.7\nfake pdf body"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()


def _head(size):
    return {"ContentLength": size}


class FileTypeTests(TestCase):
    def test_allowlist_is_checked_by_extension(self):
        self.assertIsNotNone(filetypes.lookup("Lecture 3.PDF"))
        self.assertIsNone(filetypes.lookup("malware.exe"))
        self.assertIsNone(filetypes.lookup("no-extension"))

    def test_signature_must_match_the_declared_type(self):
        pdf = filetypes.BY_EXTENSION["pdf"]
        self.assertTrue(filetypes.signature_matches(pdf, b"%PDF-1.4 ..."))
        self.assertFalse(filetypes.signature_matches(pdf, b"MZ\x90\x00 ..."))

    def test_webp_needs_both_markers_so_a_wav_is_not_accepted(self):
        webp = filetypes.BY_EXTENSION["webp"]
        self.assertTrue(filetypes.signature_matches(webp, b"RIFF\x00\x00\x00\x00WEBPVP8 "))
        self.assertFalse(filetypes.signature_matches(webp, b"RIFF\x00\x00\x00\x00WAVEfmt "))

    def test_formats_without_a_signature_are_accepted_on_size_alone(self):
        self.assertTrue(filetypes.signature_matches(filetypes.BY_EXTENSION["txt"], b"hello"))


class StorageKeyTests(TestCase):
    def test_key_is_content_addressed_and_sharded(self):
        key = storage.build_key(PDF_SHA, "Midterm 2023.pdf")
        self.assertEqual(key, f"resources/{PDF_SHA[:2]}/{PDF_SHA}/Midterm-2023.pdf")

    def test_filename_is_stripped_of_path_and_unicode_tricks(self):
        self.assertEqual(storage.safe_filename("../../etc/passwd"), "etc-passwd")
        self.assertEqual(storage.safe_filename("مُحاضرة.pdf"), "pdf")
        self.assertEqual(storage.safe_filename("..."), "file")


class UploadFlowTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(code="CS116", name="Programming")
        self.user = User.objects.create_user(
            email="student@gju.edu.jo", password="pw-for-tests-1234"
        )
        self.user.is_gju_verified = True
        self.user.save()
        self.client.force_login(self.user)

    def _start(self, **overrides):
        payload = {
            "course": "CS116",
            "type": "past_paper",
            "title": "Midterm 2023",
            "filename": "midterm.pdf",
            "size_bytes": len(PDF_BYTES),
            "sha256": PDF_SHA,
        }
        payload.update(overrides)
        with mock.patch.object(storage, "presign_put", return_value="https://bucket/put"):
            return self.client.post(
                reverse("upload-start"), payload, content_type="application/json"
            )

    def _complete(self, resource_id, *, head=None, sniff=PDF_BYTES):
        with mock.patch.object(storage, "head", return_value=head) as head_mock, mock.patch.object(
            storage, "read_range", return_value=sniff
        ), mock.patch.object(storage, "delete") as delete_mock:
            head_mock.return_value = head if head is not None else _head(len(PDF_BYTES))
            response = self.client.post(
                reverse("upload-complete", args=[resource_id]),
                content_type="application/json",
            )
        return response, delete_mock

    def test_start_reserves_a_pending_resource_and_returns_a_put_url(self):
        response = self._start()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["upload_url"], "https://bucket/put")

        resource = Resource.objects.get(pk=response.json()["resource_id"])
        self.assertEqual(resource.status, Resource.Status.PENDING)
        self.assertEqual(resource.file_key, storage.build_key(PDF_SHA, "midterm.pdf"))
        # Nothing is servable until the object is confirmed.
        self.assertIsNone(resource.upload_completed_at)

    def test_disallowed_file_type_is_refused_before_any_url_is_minted(self):
        response = self._start(filename="grades.exe")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Resource.objects.exists())

    def test_oversized_file_is_refused(self):
        with self.settings(MAX_UPLOAD_BYTES=1024):
            response = self._start(size_bytes=99_999)
        self.assertEqual(response.status_code, 400)

    def test_complete_confirms_the_object_and_leaves_it_pending_moderation(self):
        resource_id = self._start().json()["resource_id"]
        response, _ = self._complete(resource_id)
        self.assertEqual(response.status_code, 200)

        resource = Resource.objects.get(pk=resource_id)
        self.assertIsNotNone(resource.upload_completed_at)
        self.assertEqual(resource.status, Resource.Status.PENDING)

    def test_trusted_uploader_skips_the_moderation_queue(self):
        self.user.approved_uploads_count = 5
        self.user.save()
        resource_id = self._start().json()["resource_id"]
        self._complete(resource_id)
        self.assertEqual(
            Resource.objects.get(pk=resource_id).status, Resource.Status.APPROVED
        )

    def test_a_file_lying_about_its_type_is_rejected_and_the_object_deleted(self):
        resource_id = self._start().json()["resource_id"]
        response, delete_mock = self._complete(resource_id, sniff=b"MZ\x90\x00 executable")
        self.assertEqual(response.status_code, 400)
        delete_mock.assert_called_once()
        self.assertIsNone(Resource.objects.get(pk=resource_id).upload_completed_at)

    def test_size_mismatch_is_rejected_and_the_object_deleted(self):
        resource_id = self._start().json()["resource_id"]
        response, delete_mock = self._complete(resource_id, head=_head(999_999))
        self.assertEqual(response.status_code, 400)
        delete_mock.assert_called_once()

    def test_missing_object_asks_the_student_to_retry(self):
        resource_id = self._start().json()["resource_id"]
        with mock.patch.object(storage, "head", return_value=None):
            response = self.client.post(
                reverse("upload-complete", args=[resource_id]),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)

    def test_another_student_cannot_complete_someone_elses_upload(self):
        resource_id = self._start().json()["resource_id"]
        other = User.objects.create_user(email="other@gju.edu.jo", password="pw-for-tests-1234")
        self.client.force_login(other)
        response = self.client.post(
            reverse("upload-complete", args=[resource_id]),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_reuploading_a_completed_file_to_the_same_course_conflicts(self):
        resource_id = self._start().json()["resource_id"]
        self._complete(resource_id)
        self.assertEqual(self._start().status_code, 409)

    def test_retrying_an_abandoned_upload_reuses_the_row(self):
        first = self._start().json()["resource_id"]
        second = self._start().json()["resource_id"]
        self.assertEqual(first, second)

    def test_exists_lets_the_client_skip_a_duplicate_upload(self):
        resource_id = self._start().json()["resource_id"]
        self._complete(resource_id)
        response = self.client.get(
            reverse("resource-exists"), {"sha256": PDF_SHA, "course": "cs116"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["exists"])
        self.assertTrue(response.json()["in_this_course"])

    def test_exists_rejects_a_malformed_hash(self):
        self.assertEqual(
            self.client.get(reverse("resource-exists"), {"sha256": "nope"}).status_code, 400
        )


class DownloadGateTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(code="CS116", name="Programming")
        self.resource = Resource.objects.create(
            course=self.course,
            type="past_paper",
            title="Midterm 2023",
            kind=Resource.Kind.FILE,
            file_key=storage.build_key(PDF_SHA, "midterm.pdf"),
            sha256=PDF_SHA,
            size_bytes=len(PDF_BYTES),
            status=Resource.Status.APPROVED,
            upload_completed_at=datetime(2026, 1, 1, tzinfo=dt_timezone.utc),
        )
        self.url = reverse("resource-download", args=[self.resource.pk])

    def _get(self):
        with mock.patch.object(storage, "presign_get", return_value="https://bucket/get"):
            return self.client.get(self.url)

    def test_metadata_is_public_but_the_file_is_not(self):
        listing = self.client.get(reverse("resource-list"))
        self.assertEqual(listing.status_code, 200)
        body = listing.json()["results"][0]
        self.assertEqual(body["title"], "Midterm 2023")
        # The object key is the only thing standing between a stranger and the
        # bytes, so it must never appear in a public response.
        self.assertNotIn("file_key", body)

    def test_absent_term_and_instructor_serialize_as_null(self):
        # Regression: source="term.__str__" resolved to NoneType's bound method
        # instead of raising, and rendered its repr into the response.
        body = self.client.get(reverse("resource-list")).json()["results"][0]
        self.assertIsNone(body["term_label"])
        self.assertIsNone(body["instructor_name"])

    def test_anonymous_download_is_refused_with_a_code_the_spa_can_act_on(self):
        response = self._get()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "login_required")

    def test_unverified_account_is_refused(self):
        user = User.objects.create_user(email="new@gju.edu.jo", password="pw-for-tests-1234")
        self.client.force_login(user)
        response = self._get()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "not_gju_verified")

    def test_banned_account_is_refused(self):
        user = User.objects.create_user(email="bad@gju.edu.jo", password="pw-for-tests-1234")
        user.is_gju_verified = True
        user.is_banned = True
        user.save()
        self.client.force_login(user)
        self.assertEqual(self._get().json()["code"], "banned")

    def test_verified_student_gets_a_signed_url_and_the_download_is_logged(self):
        user = User.objects.create_user(email="ok@gju.edu.jo", password="pw-for-tests-1234")
        user.is_gju_verified = True
        user.save()
        self.client.force_login(user)

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], "https://bucket/get")
        self.assertEqual(Download.objects.filter(user=user, resource=self.resource).count(), 1)

    def test_pending_and_removed_resources_are_not_downloadable(self):
        user = User.objects.create_user(email="ok@gju.edu.jo", password="pw-for-tests-1234")
        user.is_gju_verified = True
        user.save()
        self.client.force_login(user)

        self.resource.status = Resource.Status.PENDING
        self.resource.save()
        self.assertEqual(self._get().status_code, 404)

        self.resource.status = Resource.Status.APPROVED
        self.resource.save()
        self.resource.soft_delete()
        self.assertEqual(self._get().status_code, 404)
