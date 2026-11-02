#!/usr/bin/env python3
"""Gate R1 (schema) and R2 (evidence) for Agent 1 to 5 outputs.

Default mode validates every payloads/agent_N.json of the offer:
  * JSON schema (schemas/worker_payload.schema.json)
  * agent_id matches file, offer_id matches, finding ids unique and prefixed A<N>-
  * every evidence quote is found on its cited page (pdftotext layer plus
    Agent 1 VLM transcriptions). EXACT or FUZZY passes, FAILED quarantines.
  * DRAWING / SCHEMATIC evidence requires a VLM transcription for that page
  * DERIVED findings must cite existing input findings and carry tool output
  * TECHNICAL_CONTRADICTION / CONFLICTING_SPECS need two verified sides

--document-map validates document_map.json against its schema and against
prescan.json (page bounds, corruption coverage, vision queue coverage).

Writes RUN_DIR/OFFER_ID/gate/validation.json. Exit 0 clean, 1 on failures.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    AGENT_IDS,
    dump_json,
    iter_payloads,
    load_json,
    load_schema,
    match_quote,
    offer_dir,
    page_text,
    validate_schema,
    vlm_file,
)

CONTRADICTION = {"TECHNICAL_CONTRADICTION"}


def validate_document_map(odir: Path, offer_id: str) -> int:
    dm_path = odir / "document_map.json"
    if not dm_path.exists():
        print(f"FAIL: {dm_path} not found. Agent 1 has not written it.")
        return 1
    dm = load_json(dm_path)
    errors = validate_schema(dm, load_schema("document_map.schema.json"))
    warnings: list[str] = []
    prescan = load_json(odir / "prescan.json") if (odir / "prescan.json").exists() else {}
    if not errors:
        n = dm["page_count"]
        if dm["offer_id"] != offer_id:
            errors.append(f"offer_id {dm['offer_id']!r} != {offer_id!r}")
        if prescan and prescan.get("page_count") and n != prescan["page_count"]:
            errors.append(f"page_count {n} != prescan page_count {prescan['page_count']}")
        ids = set()
        for s in dm["sections"]:
            if s["section_id"] in ids:
                errors.append(f"duplicate section_id {s['section_id']}")
            ids.add(s["section_id"])
            if not (1 <= s["page_start"] <= s["page_end"] <= n):
                errors.append(f"section {s['section_id']} page range {s['page_start']}-{s['page_end']} outside 1-{n}")
        covered = set()
        for s in dm["sections"]:
            covered.update(range(s["page_start"], s["page_end"] + 1))
        uncovered = sorted(set(range(1, n + 1)) - covered - set(dm["boilerplate_pages"]))
        if uncovered:
            errors.append(f"pages not assigned to any section or boilerplate: {uncovered[:40]}")
        for d in dm["drawings"]:
            tf = odir / d["transcription_file"]
            if not tf.exists():
                errors.append(f"drawing on page {d['page']} transcription missing: {d['transcription_file']}")
        if prescan:
            known = {(c["page"], c["token"]) for c in dm["data_corruption"]}
            for c in prescan.get("corruption", []):
                if (c["page"], c["token"]) not in known:
                    errors.append(f"prescan corruption {c['token']} on page {c['page']} not carried into data_corruption")
            drawn = {d["page"] for d in dm["drawings"]} | set(dm["boilerplate_pages"])
            for v in prescan.get("vision_queue", []):
                if v["page"] not in drawn and not vlm_file(odir, v["page"]).exists():
                    warnings.append(f"vision queue page {v['page']} ({', '.join(v['reasons'])}) has no drawing entry or VLM transcription")
            if prescan.get("ocr_required") and not dm["ocr_required"]:
                errors.append("prescan says ocr_required but document map says false")
    report = {"mode": "document_map", "errors": errors, "warnings": warnings}
    dump_json(odir / "gate" / "document_map_validation.json", report)
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        print("FAIL document_map:")
        for e in errors[:60]:
            print(f"  - {e}")
        return 1
    print(f"PASS document_map: {len(dm['sections'])} sections, {len(dm['drawings'])} drawings, {len(dm['data_corruption'])} corruptions")
    return 0


def check_evidence(odir: Path, quote: str, page: int, etype: str, page_count: int | None) -> dict:
    if page_count and not (1 <= page <= page_count):
        return {"status": "FAILED", "score": 0.0, "reason": f"page {page} outside 1-{page_count}"}
    if etype in ("DRAWING", "SCHEMATIC"):
        if not vlm_file(odir, page).exists():
            return {"status": "FAILED", "score": 0.0, "reason": f"{etype} evidence but no VLM transcription for page {page}"}
        status, score = match_quote(quote, page_text(odir, page, include_vlm=True))
        if status == "FAILED":
            return {"status": "FAILED", "score": score, "reason": "quote not in VLM transcription"}
        return {"status": "VLM_ONLY", "score": score}
    status, score = match_quote(quote, page_text(odir, page, include_vlm=True))
    if status == "FAILED":
        # tolerate off-by-one page citations caused by page-spanning sentences
        for adj in (page - 1, page + 1):
            if adj >= 1 and (not page_count or adj <= page_count):
                s2, sc2 = match_quote(quote, page_text(odir, adj))
                if s2 != "FAILED":
                    return {"status": "FAILED", "score": sc2, "reason": f"quote found on page {adj}, not cited page {page}"}
        return {"status": "FAILED", "score": score, "reason": "quote not found on cited page"}
    return {"status": f"VERIFIED_{status}", "score": score}


def validate_workers(odir: Path, offer_id: str, page_count: int | None) -> int:
    schema = load_schema("worker_payload.schema.json")
    results: dict = {"mode": "workers", "agents": {}, "findings": {}}
    all_findings: dict[str, dict] = {}
    had_failure = False
    payloads = list(iter_payloads(odir))
    if not payloads:
        print("FAIL: no payloads found in payloads/")
        return 1
    loaded = {}
    for num, path in payloads:
        data = load_json(path)
        errors = validate_schema(data, schema)
        if not errors:
            if data["agent_id"] != AGENT_IDS[num]:
                errors.append(f"agent_id {data['agent_id']} does not match file agent_{num}.json")
            if data["offer_id"] != offer_id:
                errors.append(f"offer_id {data['offer_id']!r} != {offer_id!r}")
            seen = set()
            for f in data["extracted_findings"]:
                if not f["finding_id"].startswith(f"A{num}-"):
                    errors.append(f"finding {f['finding_id']} must start with A{num}-")
                if f["finding_id"] in seen:
                    errors.append(f"duplicate finding_id {f['finding_id']}")
                seen.add(f["finding_id"])
                all_findings[f["finding_id"]] = f
            if not all(data["self_check"].get(k) for k in ("all_quotes_verbatim", "all_assigned_sections_read", "no_values_inferred_without_derivation")):
                errors.append("self_check has a false flag: worker admits incomplete work")
        results["agents"][str(num)] = {"schema_errors": errors, "finding_count": len(data.get("extracted_findings", []))}
        if errors:
            had_failure = True
        else:
            loaded[num] = data

    for num, data in loaded.items():
        for f in data["extracted_findings"]:
            fid = f["finding_id"]
            checks = []
            etype = f["evidence_type"]
            sup = f.get("supporting_evidence", [])
            if etype == "DERIVED":
                d = f.get("derivation")
                if not d:
                    checks.append({"status": "FAILED", "reason": "DERIVED finding without derivation block"})
                else:
                    missing = [i for i in d["input_finding_ids"] if i not in all_findings]
                    if missing:
                        checks.append({"status": "FAILED", "reason": f"derivation inputs not found: {missing}"})
                    elif not d.get("tool_output"):
                        checks.append({"status": "FAILED", "reason": "derivation lacks tool_output from normalize_units.py"})
                    else:
                        checks.append({"status": "DERIVED_OK"})
            elif f["category"] in CONTRADICTION or f["status"] == "CONFLICTING_SPECS":
                if len(sup) < 2:
                    checks.append({"status": "FAILED", "reason": "contradiction needs >= 2 supporting_evidence entries (one per side)"})
                for ev in sup:
                    checks.append(check_evidence(odir, ev["quote"], ev["page"], ev.get("evidence_type", "TEXT"), page_count) | {"page": ev["page"]})
            else:
                checks.append(check_evidence(odir, f["evidence_quote"], f["source_page"], etype, page_count) | {"page": f["source_page"]})
                for ev in sup:
                    checks.append(check_evidence(odir, ev["quote"], ev["page"], ev.get("evidence_type", "TEXT"), page_count) | {"page": ev["page"]})
            failed = [c for c in checks if c["status"] == "FAILED"]
            verdict = "FAILED" if failed else ("VLM_ONLY" if any(c["status"] == "VLM_ONLY" for c in checks) else
                                               "DERIVED_OK" if any(c["status"] == "DERIVED_OK" for c in checks) else
                                               "VERIFIED_FUZZY" if any(c["status"] == "VERIFIED_FUZZY" for c in checks) else "VERIFIED_EXACT")
            results["findings"][fid] = {"agent": num, "verdict": verdict, "checks": checks}
            if failed:
                had_failure = True

    dump_json(odir / "gate" / "validation.json", results)
    counts: dict[str, int] = {}
    for r in results["findings"].values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    for num, info in sorted(results["agents"].items()):
        tag = "FAIL" if info["schema_errors"] else "ok"
        print(f"agent_{num}: {tag} | {info['finding_count']} findings")
        for e in info["schema_errors"][:15]:
            print(f"    schema: {e}")
    print("evidence: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for fid, r in results["findings"].items():
        if r["verdict"] == "FAILED":
            reasons = "; ".join(c.get("reason", "") for c in r["checks"] if c["status"] == "FAILED")
            print(f"  FAILED {fid}: {reasons}")
    return 1 if had_failure else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--offer", required=True)
    ap.add_argument("--document-map", action="store_true")
    a = ap.parse_args()
    run_dir = Path(a.run_dir).resolve()
    odir = offer_dir(run_dir, a.offer)
    st = load_json(run_dir / "state.json")
    pc = st["offers"].get(a.offer, {}).get("page_count")
    code = validate_document_map(odir, a.offer) if a.document_map else validate_workers(odir, a.offer, pc)
    sys.exit(code)


if __name__ == "__main__":
    main()
