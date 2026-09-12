"""
Envelope encryption for GJU credentials via HashiCorp Vault's transit engine.

The app never holds the transit key material -- only a Vault token scoped to
one operation. By design, exactly one of the two tokens below is present in
any given deployment's environment:

    VAULT_ENCRYPT_TOKEN  held by the public web app. Its Vault policy allows
                          `transit/encrypt/<key>` only.
    VAULT_DECRYPT_TOKEN   held by the offline sync worker only, which has no
                          inbound internet exposure. Its policy allows
                          `transit/decrypt/<key>` only.

So a compromised web process cannot decrypt a stored credential even if it
tried: there is no decrypt token in its environment, and Vault's policy
would refuse the call regardless. See gju-vault-password-storage-decision.

Ciphertext round-trips as a `vault:v1:...` string (Vault's own format).
GjuCredential.ciphertext is a BinaryField, so callers encode/decode ASCII.
"""
from __future__ import annotations

import base64

import hvac
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _client_for(token: str, purpose: str) -> hvac.Client:
    if not token:
        raise ImproperlyConfigured(
            f"No Vault token configured for {purpose}. This deployment should "
            f"set exactly one of VAULT_ENCRYPT_TOKEN / VAULT_DECRYPT_TOKEN -- "
            f"see accounts/vault_transit.py."
        )
    return hvac.Client(url=settings.VAULT_ADDR, token=token)


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext password. Requires VAULT_ENCRYPT_TOKEN."""
    client = _client_for(settings.VAULT_ENCRYPT_TOKEN, "encrypt")
    encoded = base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    response = client.secrets.transit.encrypt_data(
        name=settings.VAULT_TRANSIT_KEY_NAME,
        plaintext=encoded,
    )
    return response["data"]["ciphertext"]


def decrypt(ciphertext: str) -> str:
    """Decrypt a `vault:v1:...` blob back to plaintext. Requires VAULT_DECRYPT_TOKEN."""
    client = _client_for(settings.VAULT_DECRYPT_TOKEN, "decrypt")
    response = client.secrets.transit.decrypt_data(
        name=settings.VAULT_TRANSIT_KEY_NAME,
        ciphertext=ciphertext,
    )
    encoded = response["data"]["plaintext"]
    return base64.b64decode(encoded).decode("utf-8")
