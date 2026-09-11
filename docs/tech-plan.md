# GJU Vault — Tech & Infrastructure Plan

## Goals that shape the tech

- **Cheap:** $0 while in development, and a few dollars a month in production.
- **Low maintenance:** managed services, with no servers to patch. A single student should be able to run it.
- **Student-driven:** anyone with a GJU account can upload, and moderation stays lightweight.
- **Fast to find things:** browse and search by course code should take seconds.
- **Familiar stack:** Django + React.

---

## Stack at a glance

| Layer | Choice | Why |
|---|---|---|
| Backend | **Django 5.x + Django REST Framework** | Known stack; ORM, migrations and admin included |
| Auth | **django-allauth** (headless mode) | Email/password, email verification and Microsoft login, with an API for SPAs |
| Moderation UI | **Django admin** | A full moderation panel with almost no code |
| Frontend | **React + TypeScript + Vite** | Known stack; fast dev server |
| UI | **Tailwind CSS** (+ shadcn/ui optional) | Fast to build, looks decent by default |
| Data fetching | **TanStack Query** | Caching, loading states and retries for API calls |
| Database | **PostgreSQL** (managed: **Neon**) | Full-text and trigram search built in; Neon free tier is plenty for metadata |
| File storage | **MinIO** (self-hosted, S3-compatible) via `django-storages` + `boto3`; swap to **S3/R2** later | Self-hosted now, cloud later with only an env-var change |
| Videos | **Links only** (YouTube / Drive / Telegram) | Hosting video is the one thing that would get expensive |
| Search | **`django.contrib.postgres`**: full-text + `pg_trgm` | No Elasticsearch/Meilisearch needed at this scale |
| Scheduled jobs | Django **management commands** run on a cron | Link checker, cleanup, backups. No Celery needed yet |
| Secrets / credential crypto | **HashiCorp Vault** (transit engine) | Encrypts opted-in students' GJU passwords; master key never leaves Vault; split encrypt/decrypt policies |
| Slide importer | **Offline worker** (separate host, no inbound internet) | Weekly Moodle fetch; the only component that can decrypt credentials |
| Email | **Resend** or **Brevo** (free tiers) over SMTP | Verification and password-reset emails |
| Backend hosting | **Render** or **Railway** | Git push to deploy, no server admin |
| Frontend hosting | **Cloudflare Pages** (free) | Static React build on a global CDN |
| DNS / domain | **Cloudflare** | Free DNS, R2 custom domain, Turnstile anti-bot |
| Errors | **Sentry** (free tier) | Know when uploads break |

---

## Architecture

```
                   gjuvault.com                 api.gjuvault.com
  Student ────▶ ┌──────────────────┐  JSON   ┌──────────────────────────┐
  (browser)     │ React (Vite)     │ ──────▶ │ Django + DRF on Render   │
      │         │ Cloudflare Pages │         │ • REST API               │
      │         └──────────────────┘         │ • allauth (auth)         │
      │                                      │ • Django admin (/admin)  │
      │                                      └──────┬──────────┬────────┘
      │                                             │          │
      │                                             ▼          ▼
      │                                    ┌────────────┐ ┌────────────┐
      │                                    │ PostgreSQL │ │ Cloudflare │
      │                                    │ (Neon)     │ │ R2 (files) │
      │                                    └────────────┘ └─────▲──────┘
      │                                                         │
      └──────────── direct upload/download via signed URLs ─────┘

  Cron (Render cron job or GitHub Actions):
    • weekly  manage.py check_links    – mark broken video/external links
    • nightly manage.py purge_removed  – delete files soft-deleted > 30 days ago
    • nightly pg_dump → R2             – database backup
  Later: Telegram bot (webhook endpoint in Django) posts new approved uploads to the group
```

- **Same parent domain** (`gjuvault.com` and `api.gjuvault.com`) lets the session cookie and CSRF work without cross-site cookie problems.
- **Files never pass through Django.** Django checks permissions and returns a short-lived signed URL, and the browser uploads or downloads directly. That keeps the server small and cheap.
- **Storage is S3-compatible from day one.** MinIO speaks the S3 API, so `boto3` presigned uploads and downloads work identically against MinIO now and against AWS S3 or Cloudflare R2 later. Moving to the cloud is a change of endpoint and keys, not a change of code.

---

## Auth

**Requirement:** only real GJU students can download or upload.

### Decided: verify with the student's real GJU credentials
Students sign in with their GJU email and **their real GJU password**. The first sign-in checks those credentials against a GJU system to prove they're a real student, and creates the Vault account.

### The flow (sign in only; the first sign-in signs you up)
1. The student enters their **`@gju.edu.jo` email + GJU password**. Only GJU domains are accepted.
2. **Email not known yet:** Django sends the credentials to the GJU verifier (see below).
   - **Success:** create the account and log the student in.
   - **Wrong credentials:** show "wrong GJU email or password."
   - **GJU unreachable or blocking us:** fall back to a **verification email** sent to the GJU inbox. Signups keep working even if GJU is down or blocks the server.
3. **Email known:** a normal password check against our own stored hash. **GJU is only contacted at signup**, so everyday logins never depend on GJU being up.

### Two separate things happen with the password at signup
1. **Verification** — prove they're a real GJU student. Handled by the GJU verifier below.
2. **A local login hash** — an **Argon2 hash** so everyday logins to the Vault don't touch GJU. This is one-way; it can never be turned back into the password.

For most students that's all. **Only if a student opts into slide auto-import** is the password *also* stored in recoverable form — see [Slide auto-import & credential handling](#slide-auto-import--credential-handling). Students who don't opt in have no recoverable password stored anywhere, only the Argon2 hash.

- **Never logged:** request bodies excluded from logs, password field scrubbed in Sentry, never in `__str__`/`__repr__`.
- Sent over HTTPS only.
- **"Forgot password?"** sends a reset link to the GJU inbox.

### The GJU verifier (platform still to be confirmed)
`accounts/gju_verifier.py` is one function, `verify(email, password) -> ok | wrong | unavailable`, so the backend can be swapped out:
- **Moodle, if GJU's e-learning runs on it (preferred):** Moodle's `/login/token.php` endpoint is the documented API the official Moodle mobile app uses to log in. It's much more stable than scraping a web page, and it's the same endpoint the importer uses. It only works if GJU's Moodle uses its own passwords (not Microsoft single sign-on) and has mobile access enabled.
- **Student portal login:** submit the portal's login form and detect success from the response. It works, but it breaks whenever the portal page changes.
- **Microsoft 365, if GJU email is on Microsoft:** scripted password logins are mostly blocked, and the importer wouldn't work either. The route would be "Sign in with Microsoft."

**Future issues (not blocking launch):** 2FA or CAPTCHA on the GJU side would break the verifier and the importer. The email-verification fallback covers signup for that case.

### Access rules
- **Decided: public catalog, gated downloads.** Anyone can browse courses and file titles, which helps adoption and SEO. Downloading and uploading require a verified GJU account.

---

## Slide auto-import & credential handling

**The feature:** an opted-in student's GJU e-learning is checked about **once a week** (lecturers post for the coming week or month, so weekly is plenty), and any new slides/PPTs are fetched and added to the archive automatically — no manual download-and-reupload. This runs unattended, without the student present, so it needs the student's credentials stored in **recoverable** form.

Storing recoverable passwords is inherently riskier than hashing. The whole design below exists to shrink the blast radius: a database dump alone reveals nothing, and the only component that can decrypt is a small offline worker with no inbound internet.

### Consent
- **Strictly opt-in.** A clear screen explains exactly what is stored, why, and that it can be turned off. Nothing is stored recoverably until the student opts in.
- **One-click revoke** deletes the ciphertext immediately and stops future syncs. The Argon2 login hash stays, so they keep their account.

### How the password is stored — envelope encryption via a vault
```
signup / opt-in (public Django app)                weekly importer (offline worker)
─────────────────────────────────                 ─────────────────────────────────
password ─▶ Vault transit ENCRYPT ─▶ ciphertext    ciphertext ─▶ Vault transit DECRYPT ─▶ password
             (encrypt-only key)          │                          (decrypt-only key)        │
                                         ▼                                                     ▼
                            gju_credentials table                                   log in to Moodle,
                            stores ONLY ciphertext                                   fetch new slides
```
- **HashiCorp Vault's transit engine** does the crypto (this is the "secure vault designed for passwords"). The master key **never leaves Vault**; the app sends data to Vault and gets ciphertext/plaintext back. The database stores only ciphertext (AES-256-GCM, authenticated).
- **Split capability — this is the key protection.** Two Vault policies:
  - The **public Django app** gets `transit/encrypt` only. It can store a new password but **cannot read any back**. So the internet-facing surface — the part most likely to be attacked — physically cannot decrypt credentials.
  - The **offline worker** gets `transit/decrypt` only, and runs on a separate host with **no inbound internet**, pulling a job queue.
- **A database dump is useless** without also compromising Vault *and* the worker's Vault credential.
- **Every decrypt is audited.** Vault's audit log records each time a student password is used, so unusual volume is detectable and alertable.
- **No extraction path in the app:** the ciphertext is on a separate `gju_credentials` model, never on a DRF serializer, never in Django admin, never logged. A test asserts the plaintext and ciphertext never appear in any API response.
- **Rotation:** Vault transit supports key rotation and rewrap without re-collecting passwords.

### The weekly importer (offline worker)
1. A scheduler (cron / `manage.py run_importer`) picks opted-in accounts due for a sync.
2. For each, it decrypts the password via Vault, mints a **fresh Moodle token** (`login/token.php`), then **discards the password from memory**.
3. Using the token, it lists the student's courses and each course's files (`core_course_get_contents`), and downloads any file whose SHA-256 isn't already stored.
4. New files are uploaded to MinIO and inserted as `approved` resources with `source = auto_import`, deduped by hash, and attributed to the course (not the individual student).
5. Failures (token rejected, course access lost) flag the account so the student can re-authenticate.

Because tokens are minted fresh each run, the 24-hour token expiry is irrelevant — the stored password re-mints one weekly.

### Residual risk, stated plainly
If an attacker fully compromises the **offline worker**, they can harvest passwords as it decrypts them. That host is therefore the thing to harden most: no inbound internet, minimal packages, restricted Vault token, alerting on the audit log. This risk cannot be fully removed while the feature exists — it can only be contained, which is what the split-capability design does.

---

## Data model (Django apps & models)

```
catalog/
  Faculty       name
  Major         faculty → Faculty, name
  Course        code (unique, e.g. "CS 116"), name, faculty → Faculty,
                majors ↔ Major (M2M)
  Instructor    name

resources/
  Resource
    course        → Course
    type          past_paper | slides | notes | video | other
    title
    term          fall | spring | summer
    year          int
    instructor    → Instructor (nullable)
    kind          file | link
    file_key      object key (MinIO/S3)  (kind = file)
    url           external link          (kind = link)
    sha256        duplicate detection    (kind = file, indexed)
    size_bytes, mime_type
    uploader      → User (nullable for auto_import)
    source        upload | telegram_import | auto_import
    status        pending | approved | rejected | removed
    link_status   ok | broken | unchecked
    created_at, approved_at, approved_by → User
  Vote          user, resource, value      (unique per user+resource)
  Report        resource, reporter, reason (broken | wrong_course | duplicate |
                inappropriate | copyright), note, status, created_at

accounts/
  User            custom user model (email as username), role: student | moderator | admin,
                  approved_uploads_count, is_banned
  GjuCredential   separate model, one-to-one → User, only exists for opted-in students
                  ciphertext        Vault-transit ciphertext of the GJU password (never plaintext)
                  opted_in_at, last_sync_at, last_sync_status
                  — never exposed on any serializer, admin, or log
```

`GjuCredential` is deliberately a **separate model**, not fields on `User`, so it's trivial to keep it off every serializer and out of the admin, and to delete on revoke.

Use a **custom user model from day one**, because swapping it later in Django is painful.

Permissions are DRF permission classes plus queryset filtering:
- Anyone: list `approved` resources (metadata only).
- Verified students: download, upload (it becomes `pending`), vote, report.
- Moderators: the Django admin with approve/reject/merge actions and the report queue.

---

## Key flows

### Upload
1. The student fills in the form (course, type, term/year, instructor) and picks a file.
2. The browser computes the file's **SHA-256** and asks `GET /api/resources/exists?sha256=…`. If the file already exists, it says so and skips the upload.
3. `POST /api/uploads/`: Django checks the account, file type (PDF, PPTX, DOCX, images, ZIP) and size (≤ 50 MB). It creates a `pending` Resource and returns a **presigned R2 PUT URL** (boto3).
4. The browser uploads straight to R2 and then calls `POST /api/uploads/{id}/complete/`. Django verifies the object exists, then checks its size and file signature (magic bytes).
5. The upload is **auto-approved** if the uploader is trusted (e.g. ≥ 5 approved uploads). Otherwise it goes to the moderation queue.

### Download
- `GET /api/resources/{id}/download/` checks the login and redirects to a **presigned GET URL** that expires in about 10 minutes.
- PDFs preview in the browser with **PDF.js** (`react-pdf`).

### Moderation (Django admin)
- The Resource admin has list filters (status, course, type), bulk actions (approve / reject / remove), and a file preview link.
- The Report admin shows open reports grouped by resource.
- Removing a resource is a **soft delete**. `purge_removed` deletes the file from R2 after 30 days.
- A **copyright takedown** report hides the file immediately until a moderator reviews it.

### Search
- A `SearchVector` over course code, course name, resource title, and instructor, stored in a `GinIndex`.
- `TrigramSimilarity` on course code and name so that "cs116", "CS-116" and "calculs" still match.

---

## Telegram import (seeding content)

1. A maintainer uses **Telegram Desktop → Export chat history** (JSON + files).
2. `manage.py import_telegram export/result.json` parses the messages and extracts files, captions, hashtags and dates.
3. It writes a **mapping CSV** (file → course/type/term guess) that humans review and correct.
4. `manage.py import_telegram --apply mapping.csv` uploads to R2, creates `approved` resources with `source = telegram_import`, and dedupes by SHA-256.

Drive and YouTube links become `link` resources and get checked by `check_links`.

---

## Security & abuse

- Upload **rate limit** (e.g. 30/day per user) with DRF throttling.
- **File type allowlist** checked against the file's actual contents, not just its extension. No executables.
- Login and signup rate limits: allauth has them built in.
- **Cloudflare Turnstile** on sign-up and upload if bots show up.
- An `is_banned` flag checked in the permission classes.
- Standard Django production settings: `DEBUG=False`, HTTPS-only secure cookies, `CSRF_TRUSTED_ORIGINS`, and `manage.py check --deploy` passing.

---

## Environments & workflow

- A **GitHub** monorepo. `main` → production auto-deploy (Render + Cloudflare Pages). PRs get preview deploys.
- **Local dev:** `docker compose up` runs Postgres. Django runs on `:8000` and Vite on `:5173` (Vite proxies `/api` so cookies just work).
- **Files in dev:** a separate R2 bucket (`gju-vault-dev`), or MinIO in docker compose so everything runs offline.
- **Config** comes from env vars (`django-environ`). Secrets never go in git.
- **GitHub Actions:** `ruff` + `pytest` for the backend and `eslint` + `tsc` + `vitest` for the frontend, on every PR.
- **Python tooling:** `uv` for dependencies. **JS:** `pnpm`.

Repo layout:
```
/backend
  manage.py
  config/            settings (base / dev / prod), urls, wsgi
  accounts/          custom user, auth endpoints
  catalog/           faculties, majors, courses, instructors
  resources/         resources, votes, reports, uploads, search
  fixtures/          seed data for faculties/majors/courses
/frontend
  src/pages, src/components, src/api
/docs                this plan
docker-compose.yml   postgres (+ minio) for local dev
```

---

## Costs

| Item | Development | Production |
|---|---|---|
| Django hosting (Render / Railway) | $0 (Render free tier, sleeps when idle) | ~$5–7/mo (always on) |
| Postgres (Neon) | $0 | $0 (free tier covers metadata for years) |
| Cloudflare R2 | $0 (≤ 10 GB) | ~50 GB of PDFs ≈ **$0.60/mo**, downloads free |
| Cloudflare Pages | $0 | $0 |
| Email (Resend / Brevo) | $0 | $0 |
| Domain | — | ~$10–15/yr |
| **Total** | **$0** | **≈ $7–10/mo** |

Free hosting that sleeps when idle is fine during development. For launch, pay for always-on hosting so the first student of the day doesn't wait about 30 seconds for the server to wake up.

---

## Milestones

1. **Foundation:** repo, Django project with a custom user, React app, docker compose, CI.
2. **Auth:** GJU-only sign-in/sign-up, GJU credential verifier, email-verification fallback, password reset.
3. **Catalog:** faculty/major/course models, seed data, browse pages, search.
4. **Files:** MinIO signed upload and download, dedupe, PDF preview.
5. **Moderation:** Django admin actions, reports, trusted-uploader auto-approve.
6. **Seed content:** Telegram export import.
7. **Slide auto-import:** Vault transit setup, split encrypt/decrypt policies, opt-in + revoke UI, offline Moodle importer, audit alerting. (Depends on confirming the LMS is Moodle.)
8. **Launch:** deploy, domain, Sentry, backups, and an announcement in the Telegram group.
9. **Later:** Microsoft sign-in, Telegram bot, voting and sorting, link checker, "request a file" board.

---

## Open questions

- [ ] Do GJU students have Microsoft 365 accounts? If so, add Microsoft sign-in later.
- [ ] What's the name and domain? (`gjuvault.com`? Check availability.)
- [ ] Where do we get the course catalog? Scrape it from GJU's study plans, or type it in by hand per faculty.
- [ ] Will the current Telegram maintainers help with the export and act as moderators?
