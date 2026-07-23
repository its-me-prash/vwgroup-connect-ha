#!/usr/bin/env python3
# Copyright 2026 Prash Balan (@its-me-prash) — GNU AGPL v3.0-or-later
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generate docs/EU_DATA_ACT_DATA_DICTIONARY.md from the official VW-Group
EU Data Act SVK DataDictionary PDFs (Continuous + Historical).

The PDFs come from the official EU Data Act portal operator page:
  https://eu-data-act.drivesomethinggreater.com/content/euda/de/de/service/data-dictionary

They are the authoritative mapping of every ``Key`` (UUID) the portal ships to a
descriptive data-point name, description, unit, technical type and data cluster.
Keeping this in-repo saves us re-deriving field meanings every time a Scout report
surfaces a bare/UUID-keyed field (e.g. the ambiguous ``open`` leaf → doors/windows/
sunroof/trunk/enginehood, disambiguated by UUID).

Usage:
  py scripts/build_eu_data_dict_doc.py \
     "<Continuous_Data.pdf>" "<Historical_Data.pdf>" [--date YYYY-MM-DD]

Point it at freshly-downloaded PDFs when the update-watch workflow flags a new
version, then commit the regenerated doc. Requires ``pdfplumber``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    sys.exit("pdfplumber required: pip install pdfplumber")

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _clean(cell: str | None) -> str:
    text = (cell or "").replace("\n", " ")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


def _clean_name(cell: str | None) -> str:
    # Data-point names are snake_case identifiers; the PDF wraps long ones and
    # pdfplumber rejoins the halves with a space. Names never contain real
    # spaces, so collapse them. Keep ``[*]`` index markers and dots.
    return re.sub(r"\s+", "", _clean(cell))


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def extract(pdf_path: str) -> list[dict[str, str]]:
    """Return one dict per (UUID) row: key/name/description/unit/type/cluster."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    cells = [_clean(c) for c in r]
                    if not cells or not _UUID.match(cells[0]):
                        continue  # header / intro / continuation noise
                    key = cells[0]
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        {
                            "key": key,
                            "name": _clean_name(r[1]) if len(r) > 1 else "",
                            "description": cells[2] if len(cells) > 2 else "",
                            "unit": (cells[3] if len(cells) > 3 else "").lstrip("'"),
                            "type": (cells[4] if len(cells) > 4 else "").lstrip("'"),
                            "cluster": cells[5] if len(cells) > 5 else "",
                        }
                    )
    return rows


def _doc_meta(pdf_path: str) -> dict[str, str]:
    """Pull the internal 'Version' + 'Date' from the PDF's intro page."""
    out = {"version": "?", "date": "?"}
    with pdfplumber.open(pdf_path) as pdf:
        head = (pdf.pages[0].extract_text() or "")
    m = re.search(r"Version:\s*([\d.]+)", head)
    if m:
        out["version"] = m.group(1)
    m = re.search(r"Date:\s*([\d.]+)", head)
    if m:
        out["date"] = m.group(1)
    return out


def _table_md(rows: list[dict[str, str]]) -> str:
    out = ["| Key (UUID) | Data Point Name | Description | Unit | Type | Cluster |",
           "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(
            "| `{key}` | `{name}` | {desc} | {unit} | {type} | {cluster} |".format(
                key=r["key"],
                name=_md_escape(r["name"]),
                desc=_md_escape(r["description"]) or "—",
                unit=_md_escape(r["unit"]) or "—",
                type=_md_escape(r["type"]) or "—",
                cluster=_md_escape(r["cluster"]) or "—",
            )
        )
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("continuous_pdf")
    ap.add_argument("historical_pdf")
    ap.add_argument("--date", default="unknown", help="extraction date (YYYY-MM-DD)")
    ap.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "docs" / "EU_DATA_ACT_DATA_DICTIONARY.md"),
    )
    args = ap.parse_args()

    cont = extract(args.continuous_pdf)
    hist = extract(args.historical_pdf)
    cmeta = _doc_meta(args.continuous_pdf)
    hmeta = _doc_meta(args.historical_pdf)

    body = f"""# EU Data Act — VW Group Vehicle Data Dictionary

> **Auto-generated — do NOT hand-edit.** Regenerate with
> `py scripts/build_eu_data_dict_doc.py <Continuous.pdf> <Historical.pdf> --date <YYYY-MM-DD>`.

This is the authoritative mapping of every EU Data Act portal `Key` (UUID) to its
descriptive data-point name, description, unit, technical type and data cluster —
the official VW-Group **SVK DataDictionary** exposed by the portal operator.

- **Source:** <https://eu-data-act.drivesomethinggreater.com/content/euda/de/de/service/data-dictionary>
- **Continuous Data** (15-minute live feed): internal version `{cmeta['version']}`, dated `{cmeta['date']}` — {len(cont)} keys.
- **Historical Data** (one-time export): internal version `{hmeta['version']}`, dated `{hmeta['date']}` — {len(hist)} keys.
- **Extracted:** {args.date}
- **Update watch:** `.github/workflows/eu-data-dict-watch.yml` checks the source page on a schedule and opens an issue when a newer dictionary is published, so we can pull the fresh PDFs and re-run the generator.

**Column meaning** (from the source docs): *Key* = the UUID the feed ships; *Data Point Name* = the descriptive name (may repeat across keys — e.g. `windows.[*].open` has one key per window index); *Description* = what it represents; *Unit* = measurement unit; *Type* = technical data type (boolean/int/enum/string/…); *Cluster* = the data area/category.

Why in-repo: the 15-minute feed sometimes ships a value under a bare/UUID-keyed leaf (e.g. `open`) without its container. This table is the deterministic UUID → container lookup, so we never re-derive a field's meaning by hand.

---

## Continuous Data (15-minute feed) — {len(cont)} keys

{_table_md(cont)}

---

## Historical Data (one-time export) — {len(hist)} keys

{_table_md(hist)}
"""
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(body, encoding="utf-8")
    print(f"wrote {outp} — continuous={len(cont)} historical={len(hist)} "
          f"({outp.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
