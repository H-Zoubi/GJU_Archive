"""
Send the reviewed mapping CSV to the archive's ingest API.

    export GJU_ARCHIVE_API=https://api.gjuarchive.com/api
    export GJU_ARCHIVE_TOKEN=<token from `manage.py create_import_bot telegram`>
    python apply.py mapping.csv /path/to/export --dry-run   # check first
    python apply.py mapping.csv /path/to/export

This talks to the backend over plain HTTP, the same way a student's browser
does for a normal upload: ask if the hash is already known, reserve a
resource and get a presigned PUT, upload the bytes straight to the bucket,
then confirm. The only backend-side difference is the bot token, which marks
the upload as `source=telegram_import` and skips the moderation queue --
see resources/views_ingest.py in the backend. This script itself never
touches the database or the bucket credentials directly.

Only rows with include=1 are sent. A row already in the archive (by hash, in
that course) is skipped, so re-running apply.py after fixing a few rows in
the CSV is safe -- it will not create duplicates for rows already imported.
"""
import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path

import requests

CHUNK = 1024 * 1024


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Importer:
    def __init__(self, api_base: str, token: str, dry_run: bool):
        self.api_base = api_base.rstrip("/")
        self.dry_run = dry_run
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Token {token}"

    def exists(self, sha256: str, course: str) -> bool:
        # Public endpoint; no auth needed, and it is the same check the
        # browser makes before a student upload -- reused as-is.
        r = self.session.get(
            f"{self.api_base}/resources/exists/",
            params={"sha256": sha256, "course": course},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["in_this_course"]

    def import_one(self, path: Path, row: dict) -> str:
        sha256 = sha256_of(path)
        if self.exists(sha256, row["course"]):
            return "skipped (already in archive)"
        if self.dry_run:
            return f"would import ({sha256[:12]}…)"

        start = self.session.post(
            f"{self.api_base}/ingest/uploads/",
            json={
                "course": row["course"],
                "type": row["type"],
                "title": row["title"] or path.stem,
                "description": row.get("caption", ""),
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256,
                "source": "telegram_import",
            },
            timeout=15,
        )
        if start.status_code == 409:
            return "skipped (duplicate reported by API)"
        start.raise_for_status()
        data = start.json()

        with path.open("rb") as fh:
            put = requests.put(
                data["upload_url"], data=fh, headers=data["headers"], timeout=120
            )
        put.raise_for_status()

        complete = self.session.post(
            f"{self.api_base}/ingest/uploads/{data['resource_id']}/complete/", timeout=30
        )
        complete.raise_for_status()
        return f"imported as resource {data['resource_id']}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mapping_csv", type=Path)
    parser.add_argument("export_dir", type=Path, help="Directory containing result.json")
    parser.add_argument("--dry-run", action="store_true", help="Hash and dedupe-check only.")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N rows.")
    args = parser.parse_args()

    api_base = os.environ.get("GJU_ARCHIVE_API")
    token = os.environ.get("GJU_ARCHIVE_TOKEN")
    if not api_base or (not token and not args.dry_run):
        sys.exit(
            "Set GJU_ARCHIVE_API (and GJU_ARCHIVE_TOKEN, unless --dry-run) in the environment."
        )

    importer = Importer(api_base, token or "", args.dry_run)

    with args.mapping_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    done = 0
    for row in rows:
        if row.get("include") != "1":
            continue
        if args.limit is not None and done >= args.limit:
            break
        path = args.export_dir / row["file_path"]
        if not row.get("course"):
            print(f"[{row['row_id']}] SKIP  no course set — {row['filename']}")
            continue
        try:
            result = importer.import_one(path, row)
        except Exception as error:  # noqa: BLE001 - report and move on to the next row
            result = f"FAILED: {error}"
        print(f"[{row['row_id']}] {result} — {row['filename']}")
        done += 1

    print(f"\nProcessed {done} row(s).")


if __name__ == "__main__":
    main()
