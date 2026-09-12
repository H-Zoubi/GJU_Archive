"""
S3-compatible object storage.

Files never pass through Django. It only mints short-lived presigned URLs and
the browser PUTs/GETs the bucket directly, which keeps the web dyno small and
the bandwidth bill on the storage provider (free egress on Cloudflare R2).

MinIO in dev and R2/S3 in production speak the same API, so swapping is an
env-var change (see S3_* in config/settings/base.py).
"""
from __future__ import annotations

import functools
import re
import unicodedata

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings


class StorageError(RuntimeError):
    """The bucket could not be reached or refused the operation."""


@functools.lru_cache(maxsize=2)
def _client(endpoint: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        # SigV4 is what MinIO, R2 and S3 all accept for presigned URLs.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def client():
    """Client for Django's own calls (head/delete), over the internal endpoint."""
    return _client(settings.S3_ENDPOINT_URL)


def _signing_client():
    """
    Client used to sign URLs handed to the *browser*.

    The signature covers the host, so a URL signed against the internal docker
    hostname would not verify when the browser hits localhost. Signing against
    the public endpoint keeps the two in agreement.
    """
    return _client(settings.S3_PUBLIC_ENDPOINT_URL or settings.S3_ENDPOINT_URL)


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str, fallback: str = "file") -> str:
    """Strip a client-supplied filename down to something safe as a key suffix."""
    name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    name = _UNSAFE.sub("-", name).strip("-.")
    # Guard against a key that is all dots/dashes, and keep keys short.
    return (name[:120] or fallback)


def build_key(sha256: str, original_filename: str) -> str:
    """
    Content-addressed object key.

    Keying by hash means an identical file re-uploaded by a second student
    lands on the same object instead of costing another copy, and it makes the
    key impossible to guess from the resource id. The two-character shard keeps
    any single prefix from growing unbounded.
    """
    return f"resources/{sha256[:2]}/{sha256}/{safe_filename(original_filename)}"


def presign_put(key: str, content_type: str, *, ttl: int | None = None) -> str:
    """URL the browser PUTs the file to. Valid for S3_UPLOAD_URL_TTL by default."""
    return _signing_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.S3_BUCKET,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=ttl or settings.S3_UPLOAD_URL_TTL,
    )


def presign_get(
    key: str,
    *,
    filename: str = "",
    inline: bool = False,
    ttl: int | None = None,
) -> str:
    """
    URL the browser downloads from.

    `inline` serves the file for in-browser preview (PDF.js) rather than
    forcing a save dialog; `filename` restores the human-readable name that the
    content-addressed key throws away.
    """
    params = {"Bucket": settings.S3_BUCKET, "Key": key}
    if filename:
        disposition = "inline" if inline else "attachment"
        params["ResponseContentDisposition"] = f'{disposition}; filename="{safe_filename(filename)}"'
    return _signing_client().generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=ttl or settings.S3_DOWNLOAD_URL_TTL,
    )


def head(key: str) -> dict | None:
    """Object metadata, or None if it is not there. Used to confirm an upload."""
    try:
        return client().head_object(Bucket=settings.S3_BUCKET, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise StorageError(str(exc)) from exc


def read_range(key: str, length: int) -> bytes:
    """First `length` bytes of an object — enough to check its magic bytes."""
    try:
        obj = client().get_object(
            Bucket=settings.S3_BUCKET, Key=key, Range=f"bytes=0-{length - 1}"
        )
    except ClientError as exc:
        raise StorageError(str(exc)) from exc
    return obj["Body"].read()


def delete(key: str) -> None:
    try:
        client().delete_object(Bucket=settings.S3_BUCKET, Key=key)
    except ClientError as exc:
        raise StorageError(str(exc)) from exc


def ensure_bucket() -> bool:
    """Create the bucket if missing. Returns True if it had to create it."""
    s3 = client()
    try:
        s3.head_bucket(Bucket=settings.S3_BUCKET)
        return False
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise StorageError(str(exc)) from exc
    try:
        s3.create_bucket(Bucket=settings.S3_BUCKET)
    except ClientError as exc:
        raise StorageError(str(exc)) from exc
    return True
