#!/usr/bin/env python3
"""Merge sharded Agent 1 outputs (document_map.part-*.json) into document_map.json.

Use when Agent 1 was sharded by page range on a long document. Sections that
span a shard boundary are joined when the same section_id appears in two
shards: page_start is the minimum and page_end the maximum.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import die, dump_json, load_json, offer_dir  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--offer", required=True)
    a = ap.parse_args()
    odir = offer_dir(Path(a.run_dir).resolve(), a.offer)
    parts = sorted(odir.glob("document_map.part-*.json"))
    if not parts:
        die("no document_map.part-*.json shards found")
    shards = [load_json(p) for p in parts]
    base = {k: v for k, v in shards[0].items() if k not in ("sections", "drawings", "data_corruption", "blank_fields", "boilerplate_pages")}
    sections: dict[str, dict] = {}
    order: list[str] = []
    drawings: dict[int, dict] = {}
    corr: dict[str, dict] = {}
    blanks: list[dict] = []
    boiler: set[int] = set()
    for s in shards:
        for sec in s["sections"]:
            sid = sec["section_id"]
            if sid in sections:
                cur = sections[sid]
                cur["page_start"] = min(cur["page_start"], sec["page_start"])
                cur["page_end"] = max(cur["page_end"], sec["page_end"])
                cur["has_tables"] = cur.get("has_tables", False) or sec.get("has_tables", False)
            else:
                sections[sid] = dict(sec)
                order.append(sid)
        for d in s["drawings"]:
            drawings[d["page"]] = d
        for c in s["data_corruption"]:
            corr[c["corruption_id"]] = c
        blanks.extend(s.get("blank_fields", []))
        boiler.update(s["boilerplate_pages"])
        base["ocr_required"] = base.get("ocr_required", False) or s.get("ocr_required", False)
    base["sections"] = [sections[sid] for sid in order]
    base["drawings"] = [drawings[p] for p in sorted(drawings)]
    base["data_corruption"] = [corr[k] for k in sorted(corr)]
    base["blank_fields"] = blanks
    base["boilerplate_pages"] = sorted(boiler)
    dump_json(odir / "document_map.json", base)
    print(f"merged {len(parts)} shards: {len(base['sections'])} sections, {len(base['drawings'])} drawings, {len(base['data_corruption'])} corruptions")


if __name__ == "__main__":
    main()
