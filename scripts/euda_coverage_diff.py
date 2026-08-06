#!/usr/bin/env python3
"""EU-Data-Act coverage diff — which official spec fields do we NOT map yet?

The SVK / EU-Data-Act Data Dictionary (``cariad/auth/eu_data_dictionary.json``,
V5.0 Continuous-Data, ~1142 fields) is the authoritative catalogue of portal
field names. Our EU-Data-Act parser (``cariad/auth/_eu_data_act.py``) maps a
curated subset onto ``VehicleData`` by field NAME (the portal returns names, not
UUIDs). This script diffs the two so we can see, proactively, which spec fields
we have never wired — the inverse of the reactive Scout (which only surfaces
fields a live car actually sent).

Grounded, offline, read-only:
  * spec names come straight from the JSON (same rule as ``_by_name()``)
  * "referenced by us" = the name (or its last dotted segment) appears as a
    string literal ANYWHERE in ``_eu_data_act.py`` (a mapped ``first()`` name, a
    synonym list entry, an enum table, …). A literal-level match deliberately
    over-counts references so the reported GAP is a safe lower bound: anything
    it lists is genuinely nowhere in the parser.

Output is a diagnostic artefact for our own triage. It is NOT posted anywhere,
and per the mapping policy it only tells us where to LOOK — every candidate
still needs a real payload to confirm the field's shape before we wire it.

Usage:
    py scripts/euda_coverage_diff.py            # human summary to stdout
    py scripts/euda_coverage_diff.py --json OUT # full machine-readable dump
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PKG = _ROOT / "custom_components" / "vag_connect"
_DICT = _PKG / "cariad" / "auth" / "eu_data_dictionary.json"
_PARSER = _PKG / "cariad" / "auth" / "_eu_data_act.py"


def load_spec() -> dict[str, dict]:
    """name -> spec entry, mirroring eu_data_dictionary._by_name() (first wins)."""
    raw = json.loads(_DICT.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for key, entry in raw.items():
        if key == "_meta" or not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name and name not in out:
            out[name] = entry
    return out


def parser_literals() -> set[str]:
    """Every string literal in _eu_data_act.py, plus each literal's last dotted
    segment (so ``battery_state_report.soc`` also registers ``soc``)."""
    tree = ast.parse(_PARSER.read_text(encoding="utf-8"))
    lits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.strip()
            if s:
                lits.add(s)
                if "." in s:
                    lits.add(s.rsplit(".", 1)[-1])
    return lits


def is_referenced(name: str, lits: set[str]) -> bool:
    if name in lits:
        return True
    # a spec name may be dotted (battery_state_report.charge_energy); count it
    # covered if either the full name or its leaf is referenced by us.
    leaf = name.rsplit(".", 1)[-1] if "." in name else name
    return leaf in lits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", metavar="OUT", help="write full JSON report here")
    args = ap.parse_args()

    spec = load_spec()
    lits = parser_literals()

    mapped: list[str] = []
    unmapped: list[str] = []
    for name in sorted(spec):
        (mapped if is_referenced(name, lits) else unmapped).append(name)

    by_cluster: dict[str, list[str]] = defaultdict(list)
    for name in unmapped:
        cluster = spec[name].get("cluster") or "(no cluster)"
        by_cluster[cluster].append(name)

    total = len(spec)
    cov = len(mapped)
    print(f"EU-Data-Act coverage: {cov}/{total} spec fields referenced "
          f"({cov * 100 // total}%), {len(unmapped)} not mapped.\n")
    print("Unmapped spec fields by cluster (priority = cluster relevance):")
    for cluster, names in sorted(by_cluster.items(), key=lambda kv: -len(kv[1])):
        print(f"\n  == {cluster} ({len(names)}) ==")
        for name in sorted(names):
            e = spec[name]
            unit = f" [{e['unit']}]" if e.get("unit") else ""
            print(f"    {name}{unit} — {e.get('type', '?')}")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "total": total, "mapped": cov, "unmapped_count": len(unmapped),
            "unmapped_by_cluster": {
                c: [{"name": n, **spec[n]} for n in sorted(v)]
                for c, v in by_cluster.items()
            },
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nFull JSON report -> {args.json}")

    # exit 0 always: this is a diagnostic, not a gate.
    return 0


if __name__ == "__main__":
    sys.exit(main())
