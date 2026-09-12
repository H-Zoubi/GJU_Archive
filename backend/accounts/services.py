"""
Opt-in / revoke for GJU Vault's automatic MyGJU data sync, and the
MyGJU-profile refresh shared by the login/signup path and the offline sync
worker.

Kept out of views.py so encrypting/deleting the credential has one call site
to audit, and out of models.py so GjuCredential itself stays a plain,
inert record (see its docstring: it must never be exposed).
"""
from __future__ import annotations

from academics.models import Major

from . import gju_verifier, vault_transit
from .gju_profile import PROFILE_URL, parse_profile
from .models import GjuCredential, StudentProfile


def opt_in_gju_sync(user, password: str) -> GjuCredential:
    """Encrypt `password` via Vault transit and store it, replacing any prior one."""
    ciphertext = vault_transit.encrypt(password).encode("ascii")
    credential, _created = GjuCredential.objects.update_or_create(
        user=user,
        defaults={"ciphertext": ciphertext},
    )
    return credential


def revoke_gju_sync(user) -> bool:
    """Delete the stored credential, if any. Returns whether one existed."""
    deleted, _ = GjuCredential.objects.filter(user=user).delete()
    return deleted > 0


def needs_profile_refresh(user) -> bool:
    """
    True if this user has no major/entry year on file yet.

    Queries directly rather than via `user.student_profile` -- that reverse
    accessor caches a "does not exist" result on `user` the first time it's
    read, and LoginView reads it here *before* refresh_profile_from_mygju
    creates the row moments later in the same request. Going through the
    cached descriptor here would make that same still-poisoned cache get
    read again when the view serializes `user` for the response, silently
    handing back a freshly-refreshed student their own stale nulls.
    """
    profile = StudentProfile.objects.filter(user=user).first()
    return profile is None or profile.major_id is None or profile.entry_year is None


def refresh_profile_from_mygju(user, password: str) -> StudentProfile:
    """
    Log into MyGJU with `password` (the plaintext already in hand for this
    request -- never a stored/decrypted one) and refresh this user's
    StudentProfile (major, entry year) from their profile page.

    Raises gju_verifier.GjuSessionError if login fails, or lets any other
    exception (network, parsing) propagate -- callers decide how to handle
    that (the login/signup path logs and continues; the sync worker records
    it against the credential). Shared so both call sites parse and store the
    page identically -- see accounts/gju_sync_worker and
    accounts/gju_profile.py's docstring for why this only ever reads major
    and entry year, never the page's other (PII) fields.
    """
    with gju_verifier.authenticated_session(user.email, password) as page:
        page.goto(PROFILE_URL, wait_until="domcontentloaded")
        html = page.content()

    data = parse_profile(html)
    major = Major.objects.filter(name=data["major_name"]).first() if data["major_name"] else None

    profile, _created = StudentProfile.objects.update_or_create(
        user=user,
        defaults={"major": major, "entry_year": data["entry_year"]},
    )
    return profile
