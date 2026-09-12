"""
Read a Telegram Desktop chat export and write a CSV mapping for a human to
review before apply.py sends anything to the archive.

    python parse.py /path/to/export/result.json --out mapping.csv

Export a chat with Telegram Desktop's "Export chat history" (JSON format,
with media downloaded) first -- this reads the result.json it produces plus
the sibling `files/`/`photos/` directories it points at.

Nothing here writes to the archive. It only ever reads the export and writes
a CSV; a human is expected to open that CSV, fix the guessed course/type/
title columns, blank the `include` column for anything not worth keeping,
and hand the corrected file to apply.py. Guessing wrong here just means more
editing, not a bad record in the archive -- apply.py is the only script that
can do that.
"""
import argparse
import csv
import json
from pathlib import Path

from common import flatten_text, guess_course, guess_type

# Kept in sync by eye with common/filetypes.ALLOWED_EXTENSIONS in the
# backend. A file outside this list would be rejected by the ingest API's
# own upload-integrity check anyway, so there is no point queuing it here.
ALLOWED_EXTENSIONS = {
    "pdf", "pptx", "docx", "xlsx", "ppt", "doc", "xls", "zip",
    "png", "jpg", "jpeg", "gif", "webp", "txt", "md",
}

FIELDNAMES = [
    "row_id", "file_path", "filename", "message_date", "caption",
    "course", "type", "title", "include", "notes",
]


def iter_file_messages(export_dir: Path, messages: list[dict]):
    for message in messages:
        file_rel = message.get("file")
        if not file_rel:
            continue
        path = export_dir / file_rel
        extension = path.suffix.lower().lstrip(".")
        caption = flatten_text(message.get("text"))
        note = ""
        include = True
        if extension not in ALLOWED_EXTENSIONS:
            include = False
            note = f"extension .{extension or '?'} not in the archive's allowlist"
        elif not path.exists():
            include = False
            note = "file missing from export (media probably not downloaded)"
        yield message, path, caption, include, note


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_json", type=Path, help="Path to the export's result.json")
    parser.add_argument("--out", type=Path, default=Path("mapping.csv"))
    args = parser.parse_args()

    export_dir = args.export_json.resolve().parent
    data = json.loads(args.export_json.read_text(encoding="utf-8"))
    messages = data.get("messages", [])

    rows = []
    skipped_no_course = 0
    for row_id, (message, path, caption, include, note) in enumerate(
        iter_file_messages(export_dir, messages), start=1
    ):
        course = guess_course(caption) or guess_course(path.name)
        if include and not course:
            skipped_no_course += 1
            note = note or "no course code found in caption or filename; fill in by hand"
        rows.append({
            "row_id": row_id,
            "file_path": str(path.relative_to(export_dir)) if path.exists() else str(path),
            "filename": path.name,
            "message_date": message.get("date", ""),
            "caption": caption.replace("\n", " ").strip()[:300],
            "course": course,
            "type": guess_type(caption) or guess_type(path.name),
            "title": (caption.strip().splitlines()[0][:255] if caption.strip() else path.stem),
            "include": "1" if include else "0",
            "notes": note,
        })

    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.out}")
    print(f"  {sum(r['include'] == '1' for r in rows)} marked include=1")
    print(f"  {skipped_no_course} have no guessed course -- review those first")
    print("Review and correct the CSV, then run apply.py against it.")


if __name__ == "__main__":
    main()
