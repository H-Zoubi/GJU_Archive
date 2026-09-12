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
| File storage | **MinIO** on the homelab (S3-compatible) via `boto3` presigned URLs; swap to **S3/R2** later | Self-hosted now, cloud later with only an env-var change |
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

*Target architecture below (Render/Neon/Cloudflare, a domain, paid hosting).
What actually runs today is the whole stack self-hosted via `docker compose up`
on a homelab — see [Environments & workflow](#environments--workflow) — which
is cheaper and simpler while there's no payment feature and no need for a CDN.
Moving to the target setup later is a hosting change, not a code change,
because storage is already S3-compatible and config is already env-driven.*

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

### The GJU verifier *(implemented)*
`accounts/gju_verifier.py` exposes one function, `verify(email, password) -> ok | wrong | unavailable`, so the backend behind it can be swapped without touching callers. GJU's e-learning is not on Moodle (that route was dropped), so the implemented backend is:
- **The MyGJU student portal**, driven by a real (stealth) Playwright/Chromium browser: MyGJU's WAF blocks plain headless HTTP requests and fingerprints headless browsers, so the verifier strips the automation fingerprint that gives it away, which lets it run fully headless in production. It submits the portal's login form and detects success from the response. This is more fragile than a documented API — it breaks whenever the portal page changes — which is why `unavailable` (not just `ok`/`wrong`) is a first-class result: it falls back to the email-verification flow instead of blocking signup.
- **A circuit breaker** (`GJU_VERIFIER_BREAKER_THRESHOLD` / `_COOLDOWN_S`) stops making live attempts for a cooldown window after several consecutive `unavailable` results, so a WAF block or portal outage can't burn the shared server's IP across a burst of signups.

**Future issues (not blocking launch):** 2FA or CAPTCHA on the GJU side would break the verifier. The email-verification fallback covers signup for that case.

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

The full, current model lives in **[docs/backend-data-model.md](backend-data-model.md)**
— this used to duplicate it inline, which let the two drift apart as the
schema grew (majors/courses/terms/offerings/schedules are all in an
`academics` app now, not `catalog`). One thing worth repeating here because it
shapes the auth design above: `GjuCredential` is deliberately a **separate
model** from `User`, one-to-one, existing only for opted-in students, so it's
trivial to keep off every serializer and out of the admin, and to delete
outright the moment a student revokes.

Use a **custom user model from day one**, because swapping it later in Django is painful.

Permissions are DRF permission classes plus queryset filtering:
- Anyone: list `approved` resources (metadata only).
- Verified students: download, upload (it becomes `pending`), vote, report.
- Moderators: the Django admin with approve/reject/merge actions and the report queue.

---

## Key flows

### Upload *(implemented)*
1. The student fills in the form (course, type, term/year, instructor) and picks a file.
2. The browser computes the file's **SHA-256** with WebCrypto and asks `GET /api/resources/exists/?sha256=…`. If the archive already has it, the upload is skipped and **nothing crosses the network**.
3. `POST /api/uploads/`: Django checks the account, the file type and the size (≤ 50 MB), reserves a `pending` Resource and returns a **presigned PUT URL** valid for 15 minutes.
4. The browser PUTs straight to the bucket, then calls `POST /api/uploads/{id}/complete/`. Django confirms the object exists, that its size matches what was declared, and that its **first bytes really are** the format the extension claimed. A mismatch deletes the object.
5. The upload is **auto-approved** if the uploader is trusted (≥ 5 approved uploads). Otherwise it waits in the moderation queue.

Nothing is served until step 4 succeeds: a row with `upload_completed_at` null is an abandoned upload, invisible to every read path and swept by `manage.py purge_files`.

**Object keys are content-addressed** — `resources/{sha[:2]}/{sha}/{safe-name}`. The same PDF uploaded by two students in two courses is one object, the key cannot be guessed from a resource id, and the two-character shard keeps any one prefix from growing unbounded. Because a key can be shared, `purge_files` only deletes an object once no live resource still points at it.

### Download *(implemented)*
- `GET /api/resources/{id}/download/` runs the entitlement check and returns a **presigned GET URL** that expires in 5 minutes, with the original filename restored via `Content-Disposition`. `?inline=1` serves it for preview instead of a save dialog.
- Every hand-out writes a `Download` row. That log is the only thing that can answer "how many downloads has this student used this month", and it cannot be reconstructed later if it is not written now — which is why it exists before any paywall does.
- PDFs preview in the browser with **PDF.js** (`react-pdf`).

### Access control & the paywall seam *(implemented)*

Every download passes through one function — `resources/entitlements.py::check_download(user, resource)` — which returns an allow, or a denial carrying a stable `code` (`login_required`, `not_gju_verified`, `banned`, `not_available`) and a message written for the student. The frontend switches on the code, so a new gate needs no API change.

Today the rule is simply: browsing is public, downloading needs a verified GJU account. **Turning on a paywall later is an edit to that one function plus a `payments` app** — not a change to the storage layer, the views or the frontend. The shapes it could take, all expressible as a new denial:

- a **quota** ("5 free downloads a month"), counted from the `Download` log;
- a **contribution rule** ("upload an approved file to unlock downloads"), counted from `approved_uploads_count`;
- a **subscription or credit balance**, from the payments app.

**Payment rails.** The requirement is Apple Pay, Visa/debit and ZainCash. That rules out Stripe (no Jordanian sellers) and largely rules out Paddle / Lemon Squeezy (no local wallets). The realistic candidates are **Amazon Payment Services** (ex-PayFort), **HyperPay** and **Tap** for cards + Apple Pay, with **ZainCash** added alongside as its own method — so the seam should be a small `PaymentProvider` interface (`create_checkout()` / `handle_webhook()`) with more than one implementation from the start. ⚠️ Confirm current Jordan onboarding and Apple Pay support with each provider directly before committing; their terms change and none of this is verified.

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

- A **GitHub** monorepo. `main` → production auto-deploy (target hosting TBD; currently self-hosted on a homelab — see below). PRs get preview deploys once CI exists.
- **Local dev / self-hosted deploy — one command:** `docker compose up` brings up the *whole* stack (Postgres, MinIO, a dev-mode Vault, Django, Vite) with zero manual setup, including loading the default academic catalog on first boot (`manage.py seed_academics`, see [docs/backend-data-model.md](backend-data-model.md)). Django runs on `:8000`, Vite on `:5173` (Vite proxies `/api` so cookies just work). Every service has a healthcheck and restarts automatically (`restart: unless-stopped`). See the top comment in `docker-compose.yml` for the hybrid mode (host backend/frontend, dockerized dependencies only).
- **Files:** MinIO in docker compose for local dev; a homelab MinIO instance or R2/S3 in production, configured entirely through `backend/.env` (`S3_ENDPOINT_URL` and friends) — no code change either way.
- **Config** comes from env vars (`django-environ`). Secrets never go in git (`backend/.env` is gitignored; `backend/.env.example` documents every variable).
- **GitHub Actions** (planned, not yet set up): `ruff` + `pytest` for the backend and `eslint` + `tsc` + `vitest` for the frontend, on every PR.

Repo layout:
```
/backend
  manage.py
  config/            settings (base / dev / prod), urls, wsgi
  accounts/          custom user, GJU verifier, Vault transit, auth endpoints
  academics/         majors, subjects, courses, study plans, terms, offerings, schedules
    fixtures/        the default catalog (gju_catalog.json) loaded by seed_academics
  resources/         resources, votes, downloads, uploads, moderation, ingest API
  moderation/        reports, audit log, takedown requests
  integrations/      importer run/mapping bookkeeping
  common/            shared abstract models, S3 storage helpers, cross-app commands
                     (e.g. reset_student_data)
  data/              study-plan PDFs and MyGJU page dumps used to build the catalog
/frontend
  src/pages, src/components, src/api
/importers/telegram  standalone one-time Telegram-export importer (own requirements.txt)
/scripts             one-off ops scripts (e.g. scripts/vault_dev_setup.sh)
/docs                this plan, and docs/backend-data-model.md
docker-compose.yml   the full stack: db, minio(+init), vault, backend, frontend
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
