# GJU Vault — Backend Data Model

Modeled to mirror GJU's real structure (from gju.edu.jo) and to leave room to grow. Each section is a Django **app**. Fields marked _(future)_ aren't needed for V1 but the schema is shaped so they slot in without a painful migration.

**Design principles**
- **People vs. identities are separate.** A *lecturer* is an academic entity that teaches courses (referenced by resources) whether or not they ever log in. A *User* is a login account. They link optionally.
- **Roles via Django Groups, not hardcoded `if`s.** One `User.role` enum for the common case, but real permissions come from Django's Group/Permission system so new roles and fine-grained rights can be added later without code changes.
- **The academic structure is reference data**, seeded and rarely edited, kept clean so browsing and the Moodle importer both hang off it.
- **Every model gets `created_at` / `updated_at`** (via an abstract `TimeStamped` base) and soft-deletable models get `is_deleted` + `deleted_at`.

---

## Structure this maps to

Schools and departments are intentionally **left out** — they're org labels that add nothing to an archive. Students browse by **major → course**, so that's the spine of the model.

```
Major   (e.g. Computer Engineering, Computer Science, Game Design, M.Sc. …)

Course  (CS116 …) — belongs to one or more majors
  └─ CourseOffering — one course taught in one term by instructor(s); maps to a Moodle course
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
  is_active/is_staff/is_superuser   (Django built-ins; superadmin ⇒ is_superuser)
  approved_uploads_count int      -- drives trusted-uploader auto-approve
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

```
Major
  name, code            -- "Computer Science", "CS"
  degree_level          enum: diploma | bachelor | master | phd
  partner_institution   nullable   -- e.g. PSUT, THWS (joint/transnational programs)
  slug
  is_active

Instructor     (a lecturer / faculty member — academic entity, may have no login)
  full_name
  title                 nullable -- Prof./Dr./Eng.
  email                 nullable
  user                  reverse O2O ← accounts.User (set if they signed up)
  is_active

Course
  code                  unique, normalized -- "CS116" (also store display "CS 116")
  name
  majors                M2M → Major            -- a course can serve several majors
  credit_hours          nullable
  level                 nullable -- 100/200/300 tier _(future)_
  description           nullable
  prerequisites         M2M → Course (self, symmetrical=False)   -- MyGJU-style prereqs
  corequisites          M2M → Course (self) _(future)_
  slug

Term            (a semester)
  season                first | second | summer
  year                  int                  -- academic year the term starts, e.g. 2025
  (unique: season+year); helper "is_current"

CourseOffering  (a "section": one course, one term, taught by instructor(s))
  course                FK → Course             -- the MyGJU-like section + Moodle hook
  term                  FK → Term
  instructors           M2M → Instructor
  section_number        nullable -- e.g. "1", "2"
  campus                nullable -- Madaba / Jabal Amman _(future)_
  language              nullable enum: english | arabic | german _(future)_
  capacity              nullable int _(future; live seat counts NOT synced — too volatile)_
  moodle_course_id      nullable int            -- set by the importer; maps Moodle → our catalog
  (unique: course+term+section_number)

MeetingTime     (a section's weekly schedule slot)   _(future — MyGJU-like)_
  offering              FK → CourseOffering
  kind                  lecture | lab | tutorial
  day_of_week           sun | mon | tue | wed | thu
  start_time, end_time
  room                  nullable -- hall/lab

ExamSchedule    (a section's exam sitting)   _(future — MyGJU-like)_
  offering              FK → CourseOffering
  kind                  midterm | final | quiz
  starts_at             datetime
  room                  nullable
```

Why the `Course ↔ Major` M2M: the same course (e.g. a shared math or German course) shows up under several majors, so students find it whichever major they browse.

Why `CourseOffering` is the center of gravity: it's simultaneously the **MyGJU-style section** (instructor, schedule, room, exams), the **archive anchor** (a resource is "CS116, Second 2025, Dr. X"), the **Moodle mapping** (`moodle_course_id`), and the raw material for **instructor course history** (below). V1 can attach resources straight to `Course` + `Term`; the richer section fields fill in as we get the data.

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
  kind                  file | link
  ── file (kind=file) ──
  file_key              object key in MinIO/S3
  sha256                indexed, for dedup
  size_bytes, mime_type, original_filename
  page_count            nullable _(future, for PDFs)_
  ── link (kind=link) ──
  url
  link_status           ok | broken | unchecked
  ── provenance & state ──
  uploader              FK → User (nullable for auto_import)
  source                upload | telegram_import | auto_import
  status                pending | approved | rejected | removed
  visibility            public_meta | gju_only          -- catalog vs. download gating
  approved_at, approved_by FK → User
  is_deleted, deleted_at  -- soft delete; purged from storage after 30 days
  created_at, updated_at

ResourceType   (fixed table/enum, extensible)
  past_paper | midterm | final | quiz | assignment | solution |
  slides | lecture_notes | summary | lab | project | book | video | other

Tag            (free-form labels, M2M to Resource)   _(future)_
  name, slug

Vote
  user, resource, value(+1)   (unique user+resource)

ResourceAttachment   _(future: multi-file resources, e.g. a full course pack)_
  resource FK, file_key, size_bytes, sha256
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

## App: `integrations` — Moodle importer & sync logs

```
ImportRun   (one execution of the weekly importer for one user)
  user                  FK → User
  started_at, finished_at
  status                success | partial | auth_failed | error
  courses_seen, files_added, files_skipped
  message               nullable

MoodleCourseMap   (learned mapping Moodle course → our catalog)
  moodle_course_id      unique
  offering              FK → CourseOffering (nullable)
  course                FK → Course (nullable)
  moodle_shortname, moodle_fullname   -- for matching/debugging
  confidence            auto | confirmed
```

The importer (offline worker) decrypts a `GjuCredential` via Vault, mints a Moodle token, walks `core_course_get_contents`, dedups by `sha256`, uploads new files to MinIO, and writes `Resource(source=auto_import)` rows plus an `ImportRun`. It never exposes the password; see the tech plan's credential section.

---

## What V1 actually builds (the rest is scaffolding)

**Concrete now:** `User`, `Major`, `Instructor`, `Course`, `Term`, `Resource`, `ResourceType`, `Report`, `AuditLog`, `Vote`.
**Shaped now, filled later:** `CourseOffering`, `MeetingTime`, `ExamSchedule`, `StudentProfile`, `GjuCredential`, `ImportRun`, `MoodleCourseMap`, `Tag`.

This keeps the first migration small while guaranteeing the big features (per-semester offerings, schedules, instructor history, the Moodle importer) don't require reshaping the core tables. Note: **instructor and course history need no new tables** — they fall out of `CourseOffering`, so building it early pays off twice.

---

## Open questions for the model

- [x] ~~Tracks / sub-majors?~~ No — dropped. Majors have no sub-majors.
- [x] ~~Semester set?~~ **First / Second / Summer.**
- [ ] Course code format: usually like `CS116` — I'll normalize codes (strip spaces/case) so `CS116`, `CS 116`, `cs-116` all match. Flag any odd formats when you seed the course list.
- [ ] **Where does section/schedule/instructor data come from?** Options: (a) enter it by hand for popular courses, (b) students fill it as they upload, (c) later, a MyGJU importer. MyGJU is login-only and a fragile JSF portal, so I'd not scrape it in V1 — offerings would be created by the Moodle importer (which knows course + term + your instructor) and by uploaders picking the semester/instructor. Confirm that's acceptable.
