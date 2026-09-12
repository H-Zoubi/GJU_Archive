"""
One-time (idempotent) setup for a *dev-mode* Vault container: enables the
transit engine, creates the gju-credentials key, writes the encrypt/decrypt
policies, and prints a fresh encrypt-only token to stdout.

This exists so `docker compose up` can bring up a working backend with zero
manual steps -- see backend/docker-entrypoint.sh, which runs this and exports
the result as VAULT_ENCRYPT_TOKEN before starting the server. It authenticates
with the dev root token (VAULT_DEV_ROOT_TOKEN), which only ever exists in the
docker-compose environment for the dev-mode Vault -- never in a real
deployment (see accounts/vault_transit.py for why prod uses AppRole instead).

Safe to re-run: enabling an already-enabled engine, recreating an existing
key, and rewriting a policy to the same rules are all no-ops in Vault. Each
run does mint a brand new token, which is fine -- dev-mode Vault keeps
nothing on disk and forgets every token on restart anyway.

Only prints the token to stdout; every other message goes to stderr so a
caller can safely do VAULT_ENCRYPT_TOKEN=$(python manage.py vault_bootstrap).
"""
import sys

import hvac
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

ENCRYPT_POLICY = """
path "transit/encrypt/{key}" {{
  capabilities = ["update"]
}}
"""

DECRYPT_POLICY = """
path "transit/decrypt/{key}" {{
  capabilities = ["update"]
}}
"""


class Command(BaseCommand):
    help = "Bootstrap a dev-mode Vault's transit engine and print a fresh encrypt token."

    def handle(self, *args, **options):
        root_token = settings.VAULT_DEV_ROOT_TOKEN
        if not root_token:
            raise CommandError(
                "VAULT_DEV_ROOT_TOKEN is not set. This command is for the "
                "docker-compose dev-mode Vault only."
            )

        key_name = settings.VAULT_TRANSIT_KEY_NAME
        client = hvac.Client(url=settings.VAULT_ADDR, token=root_token)

        self._log(f"Connecting to Vault at {settings.VAULT_ADDR} ...")
        if not client.sys.is_initialized():
            raise CommandError("Vault is not initialized -- is the dev container up?")

        try:
            client.sys.enable_secrets_engine(backend_type="transit")
            self._log("Enabled the transit secrets engine.")
        except hvac.exceptions.InvalidRequest:
            self._log("Transit secrets engine already enabled.")

        client.secrets.transit.create_key(name=key_name)
        self._log(f"Ensured transit key '{key_name}' exists.")

        client.sys.create_or_update_policy(
            name="gjuvault-encrypt", policy=ENCRYPT_POLICY.format(key=key_name)
        )
        client.sys.create_or_update_policy(
            name="gjuvault-decrypt", policy=DECRYPT_POLICY.format(key=key_name)
        )
        self._log("Wrote encrypt/decrypt policies.")

        token_response = client.auth.token.create(policies=["gjuvault-encrypt"])
        token = token_response["auth"]["client_token"]
        self._log("Issued a fresh encrypt-only token.")

        # Only the token goes to stdout -- everything above is diagnostic noise
        # on stderr so `VAULT_ENCRYPT_TOKEN=$(manage.py vault_bootstrap)` works.
        self.stdout.write(token)

    def _log(self, message):
        print(message, file=sys.stderr)
