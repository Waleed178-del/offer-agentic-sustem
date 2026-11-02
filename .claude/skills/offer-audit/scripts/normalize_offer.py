#!/usr/bin/env python3
"""Normalize every verified finding of one offer to SI units (Phase 4 step 1).

Only findings that passed validate_payload.py are used. Quarantined
findings never reach the comparison. Writes
RUN_DIR/OFFER_ID/normalized/offer_normalized.json.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import dump_json, iter_payloads, load_json, offer_dir, to_number  # noqa: E402
from normalize_units import UnitError, to_si  # noqa: E402

SCOPE_CLASS = {
    "INCLUDED_BASE": "BASE",
    "STATED": "BASE",
    "PRELIMINARY": "BASE_PRELIMINARY",
    "OPTIONAL": "OPTION",
    "ALTERNATIVE": "ALTERNATIVE",
    "EXCLUDED_FROM_SUPPLY": "EXCLUDED",
    "BUYER_SUPPLY": "BUYER_SUPPLY",
    "DERIVED_ESTIMATE": "DERIVED",
    "MISSING_DATA": "MISSING",
    "NOT_DERIVABLE": "MISSING",
    "CORRUPTED_VALUE": "CORRUPTED",
    "CONFLICTING_SPECS": "CONFLICT",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--offer", required=True)
    a = ap.parse_args()
    run_dir = Path(a.run_dir).resolve()
    odir = offer_dir(run_dir, a.offer)
    validation = load_json(odir / "gate" / "validation.json")
    gate = load_json(odir / "gate" / "gate_report.json")
    if gate["verdict"] == "LOOP":
        print("ERROR: gate verdict is LOOP. Finish Phase 3 first.", file=sys.stderr)
        sys.exit(2)
    state = load_json(run_dir / "state.json")

    records = []
    errors = []
    for num, path in iter_payloads(odir):
        for f in load_json(path)["extracted_findings"]:
            verdict = validation["findings"].get(f["finding_id"], {}).get("verdict", "FAILED")
            if verdict == "FAILED":
                continue
            rec = {
                "finding_id": f["finding_id"],
                "agent": num,
                "category": f["category"],
                "item": f["item"],
                "item_key": f["item_key"],
                "attribute": f.get("attribute") or "value",
                "raw_value": f.get("value"),
                "raw_unit": f.get("unit"),
                "si_value": None,
                "si_unit": None,
                "status": f["status"],
                "scope_class": SCOPE_CLASS.get(f["status"], "UNKNOWN"),
                "source_page": f["source_page"],
                "section_ref": f.get("section_ref"),
                "evidence_quote": f["evidence_quote"],
                "evidence_type": f["evidence_type"],
                "verification": verdict,
                "confidence": f["confidence"],
                "financial_impact": f["financial_impact"],
                "option_price": f.get("option_price"),
                "alternative_group": f.get("alternative_group"),
                "cost_adder_key": f.get("cost_adder_key"),
                "action_required": f["action_required"],
            }
            num_val = to_number(f.get("value"))
            if num_val is not None and f.get("unit"):
                try:
                    si = to_si(num_val, f["unit"])
                    rec["si_value"] = round(si["value"], 6)
                    rec["si_unit"] = si["unit"]
                except UnitError as exc:
                    rec["conversion_error"] = str(exc)
                    errors.append(f"{f['finding_id']}: {exc}")
            elif num_val is not None:
                rec["si_value"] = num_val
                rec["si_unit"] = ""
            elif f.get("value") is not None:
                rec["si_value"] = f["value"]
                rec["si_unit"] = "text"
            records.append(rec)

    out = {
        "offer_id": a.offer,
        "vendor": state["offers"][a.offer]["vendor"],
        "gate_verdict": gate["verdict"],
        "record_count": len(records),
        "conversion_errors": errors,
        "records": records,
    }
    dump_json(odir / "normalized" / "offer_normalized.json", out)
    print(f"{a.offer}: {len(records)} normalized records, {len(errors)} unit errors")
    for e in errors:
        print(f"  UNIT: {e}")


if __name__ == "__main__":
    main()
