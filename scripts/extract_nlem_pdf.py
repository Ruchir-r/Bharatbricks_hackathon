"""Parse the official NLEM 2022 PDF into a structured CSV.

The PDF is 135 pages of mostly-tabular data: numbered subsection (e.g. "6.7.2.1"),
drug name (with optional combination components), level of healthcare (P / S / T),
and dosage form(s). Multi-line cells are common.

Strategy:
  - pdfplumber's extract_tables() handles the tabular layout per page.
  - For each row, normalise: strip whitespace, collapse multi-line cells, parse
    "Level of Healthcare" into P/S/T flags.
  - Drop header rows and stray non-data noise.
  - Output columns: section, drug_name, level_p, level_s, level_t, dosage_forms, raw_section_label

Usage:
    python scripts/extract_nlem_pdf.py
Outputs:
    data/nlem_2022_real.csv
"""

from __future__ import annotations
import csv
import re
import sys
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parent.parent
PDF = REPO / "data" / "raw" / "nlem2022.pdf"
OUT = REPO / "data" / "nlem_2022_real.csv"

SECTION_RE = re.compile(r"^\d+(?:\.\d+){1,4}$")  # 6.7.2.1
LEVEL_RE = re.compile(r"\b([PST])\b", re.I)


def normalise_cell(cell: str | None) -> str:
    if not cell:
        return ""
    s = re.sub(r"\s+", " ", cell.replace("\n", " ").strip())
    return s


def parse_level(cell: str) -> tuple[bool, bool, bool]:
    """E.g. "P,S,T" or "S,T" or "P" → (P,S,T) booleans."""
    cell = (cell or "").upper()
    return ("P" in cell, "S" in cell, "T" in cell)


def is_data_row(row: list[str]) -> bool:
    """A real drug row has either a section number or a recognisable drug name + level."""
    cells = [normalise_cell(c) for c in row]
    txt = " ".join(cells).strip()
    if not txt:
        return False
    if any(h in txt.lower() for h in ("medicine", "dosage form", "level of healthcare")):
        return False
    if "list of essential" in txt.lower() or "page" in txt.lower():
        return False
    # Need at least one real-looking drug-name token (alpha)
    return any(c.isalpha() for c in txt)


def extract_rows() -> list[dict]:
    rows: list[dict] = []
    with pdfplumber.open(PDF) as pdf:
        current_section = ""
        for pg_no, page in enumerate(pdf.pages, 1):
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []
            for tbl in tables or []:
                for raw_row in tbl:
                    if not is_data_row(raw_row):
                        continue
                    cells = [normalise_cell(c) for c in raw_row]
                    # Heuristically map: first numeric-looking cell is section, then name, then level, then dosage
                    section = ""
                    drug = ""
                    level = ""
                    dosage = []
                    for c in cells:
                        if not c: continue
                        if SECTION_RE.match(c):
                            section = c
                            current_section = c
                        elif re.fullmatch(r"[PST,\s]{1,7}", c.upper()) and any(x in c.upper() for x in "PST"):
                            level = c
                        elif drug == "" and any(ch.isalpha() for ch in c):
                            drug = c
                        else:
                            dosage.append(c)
                    if not drug:
                        continue
                    p, s, t = parse_level(level)
                    if not (p or s or t):
                        # Sometimes level is concatenated into the drug or dosage cell
                        for cell in cells:
                            if any(lv in (cell or "").upper() for lv in ("P,", ",P", "P)", "(P", " P ", "P/")):
                                p = True
                            if any(lv in (cell or "").upper() for lv in ("S,", ",S", "S)", "(S", " S ", "S/")):
                                s = True
                            if any(lv in (cell or "").upper() for lv in ("T,", ",T", "T)", "(T", " T ", "T/")):
                                t = True
                    rows.append({
                        "section": current_section,
                        "drug_name": drug,
                        "level_p": p, "level_s": s, "level_t": t,
                        "dosage_forms": " | ".join(dosage)[:500],
                        "raw_level_label": level,
                        "page": pg_no,
                    })
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for r in rows:
        key = (r["drug_name"].lower(), r["section"])
        if key in seen: continue
        seen.add(key)
        out.append(r)
    return out


def main():
    if not PDF.exists():
        print(f"PDF missing: {PDF}", file=sys.stderr); sys.exit(1)
    print(f"parsing {PDF.name}...")
    rows = dedupe(extract_rows())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["section","drug_name","level_p","level_s","level_t","dosage_forms","raw_level_label","page"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} rows)")
    # quality check
    print(f"  rows with any level set: {sum(1 for r in rows if r['level_p'] or r['level_s'] or r['level_t'])}")
    print(f"  unique drugs: {len({r['drug_name'].lower() for r in rows})}")


if __name__ == "__main__":
    main()
