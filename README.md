# GJU Vault

A student-run archive of past papers, slides, and course material for the German
Jordanian University — replacing the ad-hoc Telegram group with a searchable
website where students upload and browse by **major → course**.

- **Docs:** [tech & infrastructure plan](docs/tech-plan.md) · [backend data model](docs/backend-data-model.md)
- **Stack:** Django + Django REST Framework (backend), React + Vite (frontend, later),
  PostgreSQL, MinIO/S3 for files.

## Backend — local setup

Requires Python 3.12+. From the repo root:

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# macOS/Linux:           source .venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure environment
cp backend/.env.example backend/.env      # then edit if needed

# 4. Run migrations (uses SQLite by default; no services required)
cd backend
python manage.py migrate

# 5. Create an admin account
python manage.py createsuperuser

# 6. Run the dev server
python manage.py runserver
```

Then open:
- API health check: http://localhost:8000/api/health/
- Admin / moderation panel: http://localhost:8000/admin/

### Using Postgres + MinIO (closer to production)

```bash
docker compose up -d          # starts Postgres and MinIO
```

Then set `DATABASE_URL` in `backend/.env` to the docker Postgres (see `.env.example`)
and re-run `python manage.py migrate`.

- MinIO console: http://localhost:9001 (user `minioadmin` / pass `minioadmin`)

## Apps

| App | Responsibility |
|-----|----------------|
| `accounts` | Custom `User` (email login), roles, student profiles, opt-in GJU credential |
| `academics` | Majors, instructors, courses, terms, course offerings (sections), schedules |
| `resources` | Uploaded/linked files, types, votes, tags — the archive itself |
| `moderation` | Reports, audit log, takedown requests |
| `integrations` | Moodle importer runs and course mapping |
| `common` | Shared abstract models (timestamps, soft delete) |

See [docs/backend-data-model.md](docs/backend-data-model.md) for the full model.
