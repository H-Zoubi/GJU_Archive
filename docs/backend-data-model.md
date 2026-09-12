# GJU Archive — Backend Data Model

Modeled to mirror GJU's real structure (from gju.edu.jo) and to leave room to grow. Each section is a Django **app**. Fields marked _(future)_ aren't needed for V1 but the schema is shaped so they slot in without a painful migration.

**Design principles**
- **People vs. identities are separate.** A *lecturer* is an academic entity that teaches courses (referenced by resources) whether or not they ever log in. A *User* is a login account. They link optionally.
- **Roles via Django Groups, not hardcoded `if`s.** One `User.role` enum for the common case, but real permissions come from Django's Group/Permission system so new roles and fine-grained rights can be added later without code changes.
- **The academic structure is reference data**, seeded once (see `manage.py seed_academics` and [Default data & resetting student data](../README.md#default-data--resetting-student-data)) and rarely edited by hand afterwards, kept clean so browsing and every importer hang off it.
- **Every model gets `created_at` / `updated_at`** (via an abstract `TimeStamped` base) and soft-deletable models get `is_deleted` + `deleted_at`.

---

## Structure this maps to

Schools and departments are intentionally **left out** — they're org labels that add nothing to an archive. Students browse by **major → course**, so that's the spine of the model.

```
Major   (e.g. Computer Engineering, Computer Science, Game Design, M.Sc. …)

Course  (CS116 …) — belongs to one or more majors
  └─ CourseOffering — one course taught in one term by instructor(s); a Moodle
                       course maps onto it once a Moodle importer exists
```

---

## App: `accounts` — identities, roles, credentials

```
User  (custom, AbstractBaseUser; email is the login)
  email                 unique, must be @gju.edu.jo (or configured GJU domains)
  full_name
  role                  student | lecturer | moderator | admin | superadmin
  is_email_verified     bool
  is_gju_verified       bool     -- passed the GJU credential check at signup
  is_banned             bool
  is_service_account    bool     -- a bot identity for an importer job (token auth, no session)
  is_active/is_staff/is_superuser   (Django built-ins; superadmin ⇒ is_superuser)
  approved_uploads_count int      -- drives trusted-uploader auto-approve (≥ 5)
  date_joined, last_login
  ── links ──
  instructor            O2O → academics.Instructor (nullable; set if this user IS a lecturer)
  student_profile       reverse O2O (below)

StudentProfile   (optional per-student academic info)
  user                  O2O → User
  major                 FK → academics.Major (nullable)
  entry_year            nullable
  expected_grad_year    nullable _(future)_

GjuCredential   (EXISTS ONLY for students who opt into slide auto-import)
  user                  O2O → User
  ciphertext            bytes   -- Vault-transit ciphertext of the GJU password; NEVER plaintext
  opted_in_at
  last_sync_at, last_sync_status   ok | auth_failed | error
  -- deliberately a separate model; never on any serializer/admin/log
```

### Roles & permissions
| Role | What it is | How it's enforced |
|---|---|---|
| **student** | default; verified GJU member | can upload (→ pending), download, vote, report |
| **lecturer** | a `User` linked to an `Instructor`; a real GJU faculty member who signed up | student rights + _(future)_ can claim/curate their own courses |
| **moderator** | trusted volunteer | Django admin access to the moderation queue, approve/reject/merge |
| **admin** | runs the site | moderator rights + manage catalog, users, roles |
| **superadmin** | owner | Django `is_superuser`; everything, incl. Vault/importer config |

`role` is a convenience field; actual gates are **Django Groups** (`Moderators`, `Admins`, …) mapped to permissions. New role? New group, no code change.

---

## App: `academics` — the catalog (reference data)

This is the app the [default-data seed](../README.md#default-data--resetting-student-data)
covers: `manage.py seed_academics` loads a fixture built from real MyGJU
course-section dumps and the published study-plan PDFs
(`backend/academics/fixtures/gju_catalog.json`), and it's the one app a
`reset_student_data` run never touches.

```
Major
  name, code            -- "Computer Science", "CS"
  degree_level          enum: diploma | bachelor | master | phd
  partner_institution   nullable   -- e.g. PSUT, THWS (joint/transnational programs)
  slug
  is_active

Subject         (a browsable grouping of courses, e.g. "Computer Science", "German")
  name, slug
  is_university_wide    bool  -- taken across majors (German, Arabic, Maths, Sports, ...),
                                  so it belongs to no single major
  sort_order

SubjectPrefix   (one course-code prefix, e.g. "CS", "MECH", routed to a Subject)
  prefix                unique -- several prefixes can map to one subject (GJU renumbered
                                  courses over the years, e.g. ME + MECH + TME -> Mechanical)
  subject               FK → Subject
  majors                M2M → Major  -- majors this prefix serves, as a fallback for
                                         courses no study plan mentions at all

Instructor     (a lecturer / faculty member — academic entity, may have no login)
  full_name
  title                 nullable -- Prof./Dr./Eng.
  email                 nullable
  user                  reverse O2O ← accounts.User (set if they signed up)
  is_active

Course
  code                  unique, normalized -- "CS116" (also store display "CS 116")
  name
  majors                M2M → Major            -- who takes this course, from the student's
                                                    side (see ProgramCourse below)
  code_prefix           indexed -- "CS" from "CS223", backs Subject lookups
  subject               FK → Subject (nullable)
  credit_hours          nullable
  level                 nullable -- 100/200/300 tier
  description           nullable
  prerequisites         M2M → Course (self, symmetrical=False)   -- MyGJU-style prereqs
  corequisites          M2M → Course (self, symmetrical=False)
  slug

ProgramCourse   (one line of a major's published study plan)
  major                 FK → Major
  course                FK → Course
  category              university | school | program | remedial
  requirement           compulsory | elective
  section               free text -- the plan heading this was parsed from, kept verbatim
  track                 free text -- e.g. "Automotive & E-Mobility Track"
  plan_year
  confident             bool -- False when the PDF parser had to guess; flags rows for review
  note
  (unique: major+course+track)

Term            (a semester)
  season                first | second | summer
  year                  int                  -- academic year the term starts, e.g. 2025
  (unique: season+year); helper "is_current"

CourseOffering  (a "section": one course, one term, taught by instructor(s))
  course                FK → Course             -- the MyGJU-like section + Moodle hook
  term                  FK → Term
  instructors           M2M → Instructor
  section_number        nullable -- e.g. "1", "2"
  campus                nullable _(future)_
  language              nullable enum: english | arabic | german
  capacity              nullable int (live seat counts NOT synced — too volatile)
  moodle_course_id      nullable int            -- reserved for a future Moodle importer
  (unique: course+term+section_number)

MeetingTime     (a section's weekly schedule slot — MyGJU-like)
  offering              FK → CourseOffering
  kind                  lecture | lab | tutorial
  day_of_week           sun | mon | tue | wed | thu | fri | sat
  start_time, end_time
  room                  nullable -- hall/lab

ExamSchedule    (a section's exam sitting — MyGJU-like)   _(model exists; not yet imported)_
  offering              FK → CourseOffering
  kind                  midterm | final | quiz
  starts_at             datetime
  room                  nullable
```

Why `Course.majors` vs. `ProgramCourse`: they answer different questions.
`Course.majors` is derived (from `SubjectPrefix.majors`, or from a study plan
naming the course) and says roughly "who tends to take this"; a
`ProgramCourse` row is a claim quoted from a specific plan PDF and says "this
major's plan requires this course" — with its own category/requirement, since
the same course can be compulsory in one major's plan and elective in
another's. `manage.py import_study_plans` populates `ProgramCourse` from the
PDFs; `manage.py seed_subjects` then derives `Course.majors` from whichever is
the stronger signal (a study plan mention beats the code-prefix fallback).

Why `CourseOffering` is the center of gravity: it's simultaneously the
**MyGJU-style section** (instructor, schedule, room, exams), the **archive
anchor** (a resource can be "CS116, Second 2025, Dr. X"), the eventual
**Moodle mapping** (`moodle_course_id`), and the raw material for
**instructor course history** (below). A resource can also attach straight to
`Course` + `Term` when the exact section isn't known.

### Instructor & course history (no new tables — it's all `CourseOffering`)

Because every `CourseOffering` records course + term + instructor(s), the histories students want are just queries and become pages:

- **Instructor page** → "Dr. X taught": every offering where `X` is in `instructors`, grouped by term (newest first), each row linking to that section's resources. That *is* the instructor's course history.
- **Course page** → "CS116 over time": every offering of the course by term, showing who taught it and how much material each semester has. Lets a student pick "the CS116 from the professor I have."
- **Semester view** → all offerings in a term.

Optional denormalized helpers on `Instructor` — `courses_taught_count`, `first_seen_term`, `last_seen_term` — can be added later purely for fast display; the source of truth stays `CourseOffering`.

---

## App: `resources` — the archive content

```
Resource
  course                FK → Course                     -- always known
  offering              FK → CourseOffering (nullable)  -- when we know the exact section
  term                  FK → Term (nullable)
  instructor            FK → Instructor (nullable)
  type                  ResourceType (below)
  title
  description           nullable
  tags                  M2M → Tag
  kind                  file | link
  ── file (kind=file) ──
  file_key              object key in MinIO/S3
  sha256                indexed, for dedup (unique per course, ignoring blanks)
  size_bytes, mime_type, original_filename
  upload_completed_at   nullable -- null means an abandoned upload; nothing is served
                                     from one, and `purge_files` sweeps it
  ── link (kind=link) ──
  url
  link_status           ok | broken | unchecked
  ── provenance & state ──
  uploader              FK → User (nullable for auto_import)
  source                upload | telegram_import | auto_import
  status                pending | approved | rejected | removed
  visibility            public_meta | gju_only          -- catalog vs. download gating
  approved_at, approved_by FK → User
  is_deleted, deleted_at  -- soft delete; purged from storage after a grace period
  created_at, updated_at

ResourceType   (deliberately coarse — see resources/models.py for why)
  slides | exam | assignment | notes | lab | book | video | other

Tag            (free-form labels, M2M to Resource)
  name, slug

Download   (one row per file handed out — the only source of truth for
            "how many downloads has this user used", so a future quota-based
            paywall has something to count)
  user                  FK → User (nullable)
  resource              FK → Resource
  created_at

Vote
  user, resource, value(+1)   (unique user+resource)
```

---

## App: `moderation` — reports, actions, audit

```
Report
  resource              FK → Resource
  reporter              FK → User
  reason                broken_link | wrong_course | duplicate | low_quality |
                        inappropriate | copyright
  note                  nullable
  status                open | resolved | dismissed
  handled_by            FK → User (nullable)
  created_at, resolved_at

AuditLog   (append-only; who did what)
  actor                 FK → User (nullable for system/importer)
  action                e.g. resource.approve, user.ban, credential.decrypt
  target_type, target_id
  metadata              JSON
  created_at

TakedownRequest   _(future: formal copyright/removal requests)_
  resource FK, requester_email, reason, status, created_at
```

A `copyright` report hides the resource immediately (sets `status=removed`) pending review.

---

## App: `integrations` — importer run/mapping bookkeeping

```
ImportRun   (one execution of an importer job for one user)   -- model exists;
                                                                   no scheduled worker writes it yet
  user                  FK → User
  started_at, finished_at
  status                success | partial | auth_failed | error
  courses_seen, files_added, files_skipped
  message               nullable

MoodleCourseMap   (learned mapping Moodle course → our catalog)   -- model exists;
                                                                      reserved for a future Moodle importer
  moodle_course_id      unique
  offering              FK → CourseOffering (nullable)
  course                FK → Course (nullable)
  moodle_shortname, moodle_fullname   -- for matching/debugging
  confidence            auto | confirmed
```

The weekly slide auto-import worker these models are shaped for isn't built
yet: today the GJU credential verifier
(`accounts/gju_verifier.py`) and Vault transit plumbing
(`accounts/vault_transit.py`) exist and are live at signup, but the offline
worker that would decrypt a `GjuCredential`, walk a student's courses and
write `Resource(source=auto_import)` rows is still just the plan described in
[the tech plan](tech-plan.md#slide-auto-import--credential-handling). What's
actually seeded content today: `manage.py import_mygju` (real GJU course
sections, pasted from the MyGJU portal), `manage.py import_study_plans` (the
published study-plan PDFs), and the standalone `importers/telegram/` script
(a one-time bulk import from an exported Telegram group).

---

## What's actually built vs. scaffolding

**Implemented and in everyday use:** `User`, `Major`, `Subject`, `SubjectPrefix`,
`Instructor`, `Course`, `ProgramCourse`, `Term`, `CourseOffering`,
`MeetingTime`, `Resource`, `ResourceType`, `Tag`, `Vote`, `Download`, `Report`,
`AuditLog`, `StudentProfile`, `GjuCredential`.
**Modeled, not yet populated by a running process:** `ExamSchedule`,
`TakedownRequest`, `ImportRun`, `MoodleCourseMap` — the schema is shaped so
these slot in without a migration once the corresponding feature (exam-time
scraping, formal takedown flow, the Moodle worker) is built.

Note: **instructor and course history need no new tables** — they fall out of
`CourseOffering`, so building it early paid off twice.

---

## Resolved questions

- [x] ~~Tracks / sub-majors?~~ No — dropped. Majors have no sub-majors.
- [x] ~~Semester set?~~ **First / Second / Summer.**
- [x] ~~Course code format?~~ Normalized on write (`academics.normalize_code`): strips spaces/case so `CS116`, `CS 116`, `cs-116` all match; `display_code` keeps the human-readable form.
- [x] ~~Where does section/schedule/instructor data come from?~~ `manage.py import_mygju`, fed by course-section pages pasted/saved from the real MyGJU portal (see `backend/data/README.md`) — a real Moodle importer was never needed for this part.
