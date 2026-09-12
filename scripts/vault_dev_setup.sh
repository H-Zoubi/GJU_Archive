#!/usr/bin/env bash
# One-time setup for the dev-mode Vault container (docker-compose's `vault`
# service): enables the transit engine, creates the gju-credentials key, and
# prints an encrypt-only token (for backend/.env's VAULT_ENCRYPT_TOKEN) and a
# decrypt-only token (for the sync worker's .env VAULT_DECRYPT_TOKEN).
#
# Dev mode keeps nothing on disk, so re-run this after every `docker compose
# up vault` restart. This is NOT the production setup -- production uses a
# persisted, properly-initialized-and-unsealed Vault with its own policies
# applied the same way, but real tokens issued via AppRole, not `token create`.
set -euo pipefail

export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=dev-root-token

docker compose exec -e VAULT_ADDR -e VAULT_TOKEN vault vault secrets enable transit || true
docker compose exec -e VAULT_ADDR -e VAULT_TOKEN vault vault write -f transit/keys/gju-credentials

docker compose exec -e VAULT_ADDR -e VAULT_TOKEN vault vault policy write gjuvault-encrypt - <<'EOF'
path "transit/encrypt/gju-credentials" {
  capabilities = ["update"]
}
EOF

docker compose exec -e VAULT_ADDR -e VAULT_TOKEN vault vault policy write gjuvault-decrypt - <<'EOF'
path "transit/decrypt/gju-credentials" {
  capabilities = ["update"]
}
EOF

echo
echo "VAULT_ENCRYPT_TOKEN (put in backend/.env):"
docker compose exec -e VAULT_ADDR -e VAULT_TOKEN vault vault token create -policy=gjuvault-encrypt -field=token

echo
echo "VAULT_DECRYPT_TOKEN (put in the sync worker's .env only):"
docker compose exec -e VAULT_ADDR -e VAULT_TOKEN vault vault token create -policy=gjuvault-decrypt -field=token
echo
