"""
Opt-in / revoke for GJU Vault's automatic MyGJU data sync.

Kept out of views.py so encrypting/deleting the credential has one call site
to audit, and out of models.py so GjuCredential itself stays a plain,
inert record (see its docstring: it must never be exposed).
"""
from __future__ import annotations

from . import vault_transit
from .models import GjuCredential


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
