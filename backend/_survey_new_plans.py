"""One-off: check the new plans use the same numbered-heading structure."""
import re
from pathlib import Path

import pdfplumber

PLANS = Path(r"C:\dev\GJUArchive\backend\data\study_plans")
NEW = {"CS", "IA", "LS", "MGTS", "BIDA", "NUR"}

SECTION = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][^:]{3,60}):", re.IGNORECASE)

for pdf_path in sorted(PLANS.glob("*.pdf")):
    if pdf_path.stem not in NEW:
        continue
    found = []
    with pdfplumber.open(pdf_path) as pdf:
        pages = len(pdf.pages)
        for number, page in enumerate(pdf.pages, 1):
            for line in (page.extract_text() or "").splitlines():
                match = SECTION.match(line.strip())
                if match:
                    found.append((number, match.group(1), match.group(2).strip()))
    print(f"\n=== {pdf_path.stem}  ({pages} pages, {len(found)} numbered headings)")
    for page_no, num, title in found[:22]:
        print(f"    p{page_no:<3} {num:<6} {title[:62]}")
