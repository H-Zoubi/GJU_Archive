"""
Upload-integrity check shared by the student upload flow and the ingest API.

Both hand the browser (or an importer job) a presigned PUT and only trust
what actually landed in the bucket afterwards — same three checks, same
rejection behaviour — so the check lives once rather than drifting between
`UploadCompleteView` and `IngestUploadCompleteView`.
"""
from django.conf import settings

from common import filetypes, storage


def verify_uploaded_file(resource) -> str | None:
    """
    Confirm the object in the bucket matches what `resource` declared.

    Returns an error message (having already deleted the bad object) if the
    upload should be rejected, or None if it checks out. On success this also
    updates `resource.size_bytes` to the object's real size — the caller is
    still responsible for saving.
    """
    head = storage.head(resource.file_key)
    if head is None:
        return "The file did not arrive. Please try the upload again."

    actual_size = head["ContentLength"]
    if actual_size > settings.MAX_UPLOAD_BYTES or actual_size != resource.size_bytes:
        storage.delete(resource.file_key)
        return "The uploaded file does not match what was declared."

    file_type = filetypes.lookup(resource.original_filename)
    sniff = storage.read_range(resource.file_key, filetypes.SNIFF_BYTES)
    if file_type is None or not filetypes.signature_matches(file_type, sniff):
        storage.delete(resource.file_key)
        return "That file is not the type its name claims to be."

    resource.size_bytes = actual_size
    return None
