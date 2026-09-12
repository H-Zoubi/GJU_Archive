#!/bin/sh
# Entrypoint for the `backend` docker-compose service only. Bare-metal /
# venv dev still runs `python manage.py runserver` directly and is
# unaffected by anything here.
set -eu

if [ -n "${VAULT_DEV_ROOT_TOKEN:-}" ]; then
  # Always regenerate, even if a VAULT_ENCRYPT_TOKEN came in from a
  # contributor's own backend/.env (leftover from bare-metal dev): dev-mode
  # Vault forgets every token on restart, so a token from a previous
  # container is guaranteed stale, not just possibly stale.
  echo "Bootstrapping dev-mode Vault (transit engine, key, policies, token)..." >&2
  export VAULT_ENCRYPT_TOKEN="$(python manage.py vault_bootstrap)"
fi

python manage.py migrate --noinput

# Ensures the default catalog (majors, courses, terms, offerings, ...) exists.
# A no-op once it's there, so this is safe to run on every container start --
# it only matters the first time a fresh (or reset) database comes up. Never
# touches student/file data -- see `manage.py reset_student_data` for that.
python manage.py seed_academics

exec "$@"
