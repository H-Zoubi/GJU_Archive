# MyGJU course-section dumps

Drop the raw MyGJU **Course Sections** pages here as plain text, then import them.

## How to save a page

1. In MyGJU: **Academic Affairs → Course Sections**.
2. Set **Year** and **Semester**, press **Search**, and let all rows render
   (use the pager if the results span multiple pages — save one file per page,
   or set the page size large enough to get them all at once).
3. Select the whole results table, copy, and paste into a `.txt` file here.
   Copying from the browser keeps the tab characters between columns, which is
   what the parser uses to find the `CODE / NAME / SECTION` header rows.

Suggested names:

| File | Page |
|---|---|
| `mygju_first_2026.txt` | Year 2026/2027, Semester First |
| `mygju_first_2025.txt` | Year 2025/2026, Semester First |
| `mygju_summer_2025.txt` | Year 2025/2026, Semester Summer |

## How to import

```bash
python manage.py import_mygju data/mygju_first_2026.txt
python manage.py import_mygju data/mygju_first_2025.txt
python manage.py import_mygju data/mygju_summer_2025.txt
```

The year and semester are read from the page's own filter block, so usually no
flags are needed. Two exceptions:

- A page exported with **Semester = All** mixes terms and cannot be attributed —
  pass `--season first|second|summer` (and re-export per semester instead).
- `--year` overrides the detected academic year.

Add `--dry-run` to parse and report without touching the database.

Importing is **idempotent**: re-running replaces that offering's instructors and
meeting times, so you can safely re-import a corrected page.

Live seat counts (`No. of Students`) are deliberately **not** imported — they
change by the minute and mean nothing in an archive. Capacity is kept.

These `.txt` dumps are gitignored: they're large, and anyone can regenerate them
by saving the page again.
