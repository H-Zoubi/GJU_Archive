# GJU Archive

A student-run archive of past papers, slides, and course material for the German
Jordanian University — replacing the ad-hoc Telegram group with a searchable
website where students upload and browse by **major → course**.

- **Docs:** [tech & infrastructure plan](docs/tech-plan.md) · [backend data model](docs/backend-data-model.md)
- **Stack:** Django + Django REST Framework (backend), React + Vite (frontend),
  PostgreSQL, MinIO/S3 for files, HashiCorp Vault for credential encryption.

## Quick start — Docker (recommended)

Requires Docker and Docker Compose. From the repo root:

```bash
docker compose up
```

This brings up the whole stack with zero manual setup: Postgres, MinIO
(S3-compatible storage), a dev-mode Vault, the Django backend and the Vite
frontend. On first boot the backend automatically:

1. runs migrations,
2. bootstraps the dev Vault's transit engine and mints itself an encrypt
   token (see [`backend/docker-entrypoint.sh`](backend/docker-entrypoint.sh)),
3. loads the default GJU catalog — every major, course, term and section this
   project has already gathered from MyGJU and the published study plans —
   if the database doesn't have one yet (see
   [Default data & resetting](#default-data--resetting-student-data)).

Then open:
- **Frontend:** http://localhost:5173
- **API health check:** http://localhost:8000/api/health/
- **Admin / moderation panel:** http://localhost:8000/admin/
- **MinIO console:** http://localhost:9001 (user `minioadmin` / pass `minioadmin`)

Create yourself an admin account once the backend is up:

```bash
docker compose exec backend python manage.py createsuperuser
```

Every service has a healthcheck, and `restart: unless-stopped` means the
stack comes back on its own after a reboot or crash — see
[docker-compose.yml](docker-compose.yml) for the full topology.

### Hybrid mode (host backend/frontend, dockerized dependencies)

Faster reload and easier debugging: run just the dependencies in Docker and
the two apps on the host.

```bash
docker compose up db vault minio minio-init
```

```bash
# Backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
playwright install chromium   # needed by the GJU credential verifier
cp backend/.env.example backend/.env
scripts/vault_dev_setup.sh    # one-time: prints Vault tokens for backend/.env
cd backend
python manage.py migrate
python manage.py seed_academics
python manage.py createsuperuser
python manage.py runserver
```

```bash
# Frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to Django on
port 8000, so session and CSRF cookies work as one origin.

Prefer plain SQLite with no services at all? Skip the `docker compose up` line
above and leave `DATABASE_URL` unset in `backend/.env` — everything else is
the same.

## Auth

Sign-in only — there is no separate sign-up form. Entering an `@gju.edu.jo`
email for the first time checks the password against the real GJU student
portal (`backend/accounts/gju_verifier.py`, a stealth Playwright browser —
MyGJU's WAF blocks plain headless requests): on success the account is
created on the spot and the student is signed in. The password is then stored
only as an Argon2 hash for the local login; GJU is never contacted again for
that account unless the student later opts into weekly slide auto-import,
which stores the password recoverably via Vault's transit engine (see the
[tech plan](docs/tech-plan.md#slide-auto-import--credential-handling)).

## Default data & resetting student data

The database splits into two kinds of data:

- **The academic catalog** (majors, courses, subjects, terms, sections,
  schedules) — reference data seeded from a fixture built out of real MyGJU
  and study-plan data. It's meant to always be there.
- **Everything else** — accounts, uploaded/linked resources, votes,
  downloads, moderation reports — created by real use of the site.

```bash
# Ensure the catalog is loaded (no-op if it already is; runs automatically on
# every container start, see backend/docker-entrypoint.sh)
python manage.py seed_academics

# Force-reload the catalog fixture even if one is already present
python manage.py seed_academics --force

# Wipe every student/file-related row and start over, WITHOUT touching the
# catalog. Superuser accounts are kept by default. Destructive — asks for
# confirmation unless --yes is passed.
python manage.py reset_student_data
python manage.py reset_student_data --yes
python manage.py reset_student_data --yes --include-superusers
```

`docker compose exec backend python manage.py reset_student_data` runs it
against the dockerized stack.

The catalog fixture itself (`backend/academics/fixtures/gju_catalog.json`) is
rebuilt by re-running the import pipeline and re-dumping it:

```bash
python manage.py fetch_study_plans        # download the published study-plan PDFs
python manage.py import_mygju <dump.txt>  # course sections, saved from MyGJU
python manage.py import_study_plans       # mandatory/elective classification
python manage.py seed_gju                 # majors + terms
python manage.py seed_subjects            # subject groupings + course<->major links
python manage.py dumpdata academics --indent 2 -o backend/academics/fixtures/gju_catalog.json
```

## Apps

| App | Responsibility |
|-----|----------------|
| `accounts` | Custom `User` (email login), roles, student profiles, GJU credential verifier, opt-in Vault-encrypted credential storage |
| `academics` | Majors, subjects, instructors, courses, study-plan requirements, terms, course offerings (sections), schedules |
| `resources` | Uploaded/linked files, types, votes, tags, moderation queue, ingest API — the archive itself |
| `moderation` | Reports, audit log, takedown requests |
| `integrations` | Importer run/mapping bookkeeping |
| `common` | Shared abstract models, S3-compatible storage helpers, cross-app management commands (e.g. `reset_student_data`) |

See [docs/backend-data-model.md](docs/backend-data-model.md) for the full model.

## Standalone importers

`importers/telegram/` is a separate script (own `requirements.txt`) for a
one-time bulk import of an exported Telegram group's chat history into the
archive via the ingest API — see the [tech plan](docs/tech-plan.md#telegram-import-seeding-content).
