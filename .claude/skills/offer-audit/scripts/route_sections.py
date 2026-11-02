#!/usr/bin/env python3
"""Slice the Document Map into per-worker dispatch files (Phase 2).

Writes RUN_DIR/OFFER_ID/dispatch/agent_{2,3,4,5}.json. Each file lists the
sections, page ranges, drawings, corruption ids and blank fields the worker
owns. Agent 5 always receives the whole document plus every lexicon hit.

Routing rules (references/domain_taxonomy.md):
  primary owner from DOMAIN_OWNER, plus secondary routing by title keywords
  so cross-cutting sections (for example press oil cooling water) reach the
  utilities auditor as well.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DOMAIN_OWNER, SKILL_DIR, die, dump_json, load_json, load_schema, offer_dir, validate_schema  # noqa: E402

SECONDARY = {
    3: re.compile(r"utilit|consumption|cooling water|compressed air|natural gas|\bgas\b|power supply|installed power|burner|combustion|heat", re.I),
    2: re.compile(r"press|hydraulic|container|ram|stem|die holder|billet|shear|pump", re.I),
    4: re.compile(r"puller|saw|run.?out|cooling (?:table|bed|belt)|stretcher|transfer|stacker|basket|conveyor|handling", re.I),
}
AGENT_SPECS = {
    2: "agent-2-press-hydraulics.md",
    3: "agent-3-thermal-utilities.md",
    4: "agent-4-downstream-handling.md",
    5: "agent-5-risk-redteam.md",
}


def pages_of(sections: list[dict]) -> list[int]:
    pages: set[int] = set()
    for s in sections:
        pages.update(range(s["page_start"], s["page_end"] + 1))
    return sorted(pages)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--offer", required=True)
    a = ap.parse_args()
    run_dir = Path(a.run_dir).resolve()
    odir = offer_dir(run_dir, a.offer)
    dm_path = odir / "document_map.json"
    dm = load_json(dm_path)
    errs = validate_schema(dm, load_schema("document_map.schema.json"))
    if errs:
        die("document_map.json fails schema, run validate_payload.py --document-map first:\n  " + "\n  ".join(errs[:20]))
    prescan = load_json(odir / "prescan.json") if (odir / "prescan.json").exists() else {}
    state = load_json(run_dir / "state.json")
    req = state.get("inputs", {}).get("requirements")

    assigned: dict[int, list[dict]] = {2: [], 3: [], 4: []}
    for s in dm["sections"]:
        owner = DOMAIN_OWNER.get(s["domain"], 5)
        targets = {owner} if owner in assigned else set()
        for agent, rx in SECONDARY.items():
            if agent != owner and rx.search(s["title"]) and s["domain"] not in ("COMMERCIAL", "SCOPE_SPLIT"):
                targets.add(agent)
        for t in targets:
            entry = dict(s)
            entry["role"] = "PRIMARY" if t == owner else "SECONDARY"
            assigned[t].append(entry)

    def domain_items(items: list[dict], agent: int) -> list[dict]:
        out = []
        for it in items:
            dom = (it.get("owning_domain") or "").upper()
            if not dom or DOMAIN_OWNER.get(dom, 5) == agent:
                out.append(it)
        return out

    common = {
        "offer_id": a.offer,
        "vendor": dm.get("vendor", state["offers"][a.offer]["vendor"]),
        "run_dir": str(run_dir),
        "offer_dir": str(odir),
        "skill_dir": str(SKILL_DIR),
        "corpus_pages_dir": str(odir / "corpus" / "pages"),
        "full_text": str(odir / "corpus" / "full_text.txt"),
        "pdf_path": state["offers"][a.offer]["pdf_path"],
        "document_map": str(dm_path),
        "requirements": req,
        "payload_schema": str(SKILL_DIR / "schemas" / "worker_payload.schema.json"),
    }
    for agent in (2, 3, 4):
        secs = assigned[agent]
        pages = pages_of(secs)
        d = dict(common)
        d.update({
            "agent": agent,
            "spec": str(SKILL_DIR / "agents" / AGENT_SPECS[agent]),
            "output": str(odir / "payloads" / f"agent_{agent}.json"),
            "sections": secs,
            "required_section_ids": [s["section_id"] for s in secs if s["role"] == "PRIMARY"],
            "pages": pages,
            "drawings": [dr for dr in dm["drawings"] if dr["page"] in pages],
            "corruption": [c for c in domain_items(dm["data_corruption"], agent) if c["page"] in pages or c.get("owning_domain")],
            "blank_fields": [b for b in domain_items(dm.get("blank_fields", []), agent) if b["page"] in pages or b.get("owning_domain")],
        })
        dump_json(odir / "dispatch" / f"agent_{agent}.json", d)
        print(f"agent_{agent}: {len(secs)} sections, {len(pages)} pages, {len(d['drawings'])} drawings, {len(d['corruption'])} corruptions")

    d5 = dict(common)
    d5.update({
        "agent": 5,
        "spec": str(SKILL_DIR / "agents" / AGENT_SPECS[5]),
        "output": str(odir / "payloads" / "agent_5.json"),
        "sections": dm["sections"],
        "required_section_ids": [s["section_id"] for s in dm["sections"] if DOMAIN_OWNER.get(s["domain"], 5) == 5],
        "pages": list(range(1, dm["page_count"] + 1)),
        "drawings": dm["drawings"],
        "corruption": dm["data_corruption"],
        "blank_fields": dm.get("blank_fields", []),
        "lexicon_hits_file": str(odir / "prescan.json"),
        "lexicon_hit_counts": prescan.get("lexicon_hit_counts", {}),
    })
    dump_json(odir / "dispatch" / "agent_5.json", d5)
    print(f"agent_5: full document, {dm['page_count']} pages, lexicon hits {sum(d5['lexicon_hit_counts'].values())}")
    unowned = [s["section_id"] for s in dm["sections"] if s["domain"] not in DOMAIN_OWNER]
    if unowned:
        print(f"WARNING: sections with unknown domain routed to Agent 5 only: {unowned}")


if __name__ == "__main__":
    main()
