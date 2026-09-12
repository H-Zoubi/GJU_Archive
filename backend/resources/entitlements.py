"""
The single gate every download passes through.

Today access is free for any signed-in GJU member. The point of routing all of
it through one function is that turning on a paywall later is an edit *here*
plus a `payments` app — not a rewrite of the storage layer, the views or the
frontend. The shapes a gate could take, all expressible as a new Denial:

  * a quota ("5 free downloads a month"), counted from the Download log below;
  * a contribution rule ("upload an approved file to unlock downloads"),
    counted from User.approved_uploads_count;
  * a subscription or credit balance, looked up from a future payments app.

Because every denial carries a machine-readable `code`, the frontend can react
to a new gate without the API contract changing.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Resource


@dataclass(frozen=True)
class Decision:
    allowed: bool
    # Stable identifier the frontend switches on: "", "login_required",
    # "not_gju_verified", "banned", "not_available".
    code: str = ""
    # Human-readable, safe to show to the student as-is.
    detail: str = ""

    def __bool__(self) -> bool:
        return self.allowed


ALLOWED = Decision(allowed=True)


def _deny(code: str, detail: str) -> Decision:
    return Decision(allowed=False, code=code, detail=detail)


def check_download(user, resource: Resource) -> Decision:
    """Whether `user` may download `resource` right now."""
    if resource.status != Resource.Status.APPROVED or resource.is_deleted:
        return _deny("not_available", "This file is not available.")
    if resource.kind != Resource.Kind.FILE or not resource.file_key:
        return _deny("not_available", "This resource has no file to download.")

    if not user or not user.is_authenticated:
        return _deny("login_required", "Sign in with your GJU account to download.")
    if user.is_banned:
        return _deny("banned", "This account has been banned.")

    # Browsing is public; downloading is not. Keeping the check on the account
    # rather than on the resource means a future paywall applies uniformly.
    if not user.is_gju_verified:
        return _deny(
            "not_gju_verified",
            "Verify your GJU account to download files.",
        )

    return ALLOWED


def check_upload(user) -> Decision:
    """Whether `user` may upload at all. Rate limiting is separate (DRF throttle)."""
    if not user or not user.is_authenticated:
        return _deny("login_required", "Sign in with your GJU account to upload.")
    if user.is_banned:
        return _deny("banned", "This account has been banned.")
    if not user.is_gju_verified:
        return _deny("not_gju_verified", "Verify your GJU account to upload files.")
    return ALLOWED
