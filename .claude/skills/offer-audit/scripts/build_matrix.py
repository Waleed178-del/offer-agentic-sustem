#!/usr/bin/env python3
"""Build the Scope-Adjusted Comparison Matrix (Phase 4 step 3).

Inputs:  RUN_DIR/<offer>/normalized/offer_normalized.json for every offer
         RUN_DIR/<offer>/gate/gate_report.json
         RUN_DIR/comparison/alignment.json   (Agent 6)
         cost book from state.json inputs (optional)
Outputs: RUN_DIR/comparison/matrix.json
         RUN_DIR/comparison/parity.csv, landed_cost.csv, branches.csv, dossier.csv

All arithmetic happens here. Prices that are not in the offer or the cost
book are reported as UNPRICED and counted. Nothing is estimated silently.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import die, dump_json, load_json, load_schema, validate_schema  # noqa: E402

TECH_CATEGORIES = {"TECHNICAL_SPEC", "PERFORMANCE_GUARANTEE", "UTILITY_CONSUMPTION", "CONFIGURATION_ALTERNATIVE", "INCOMPLETE_SPECIFICATION", "DATA_CORRUPTION", "TECHNICAL_CONTRADICTION"}
PREFERENCE = ["BASE", "BASE_PRELIMINARY", "DERIVED", "OPTION", "ALTERNATIVE", "CONFLICT", "MISSING", "CORRUPTED", "UNKNOWN"]
PER_TONNE_UNITS = {"Nm3/h": "Nm3/t", "kW": "kWh/t", "m3/h": "m3/t"}


def fx_convert(amount: float, currency: str, report_ccy: str, fx: dict) -> float | None:
    if currency == report_ccy:
        return amount
    rate = fx.get(currency)
    if rate is None:
        return None
    return amount * rate


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    a = ap.parse_args()
    run_dir = Path(a.run_dir).resolve()
    state = load_json(run_dir / "state.json")
    comp = run_dir / "comparison"
    align_path = comp / "alignment.json"
    if not align_path.exists():
        die("comparison/alignment.json missing. Dispatch Agent 6 first.")
    align = load_json(align_path)
    errs = validate_schema(align, load_schema("alignment.schema.json"))
    if errs:
        die("alignment.json fails schema (loop Agent 6):\n  " + "\n  ".join(errs[:30]))

    cost_book = None
    if state.get("inputs", {}).get("cost_book"):
        cost_book = load_json(Path(state["inputs"]["cost_book"]))
    offers = align["offers"]
    report_ccy = align.get("report_currency") or (cost_book or {}).get("currency") or "EUR"
    fx = dict((cost_book or {}).get("fx_to_report_currency") or {})
    fx.update(align.get("fx_rates_to_report_currency") or {})
    fx = {k: v for k, v in fx.items() if isinstance(v, (int, float))}

    norm: dict[str, dict] = {}
    gates: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for oid in offers:
        p = run_dir / oid / "normalized" / "offer_normalized.json"
        if not p.exists():
            die(f"{p} missing. Run normalize_offer.py --offer {oid}")
        norm[oid] = load_json(p)
        gates[oid] = load_json(run_dir / oid / "gate" / "gate_report.json")
        for r in norm[oid]["records"]:
            by_id[r["finding_id"] + "@" + oid] = r

    alias = {}
    for al in align["key_aliases"]:
        alias[(al["offer_id"], al["from_key"], al.get("from_attribute") or "*")] = (al["to_key"], al.get("to_attribute"))

    def canon(oid: str, r: dict) -> tuple[str, str]:
        hit = alias.get((oid, r["item_key"], r["attribute"])) or alias.get((oid, r["item_key"], "*"))
        if hit:
            return hit[0], hit[1] or r["attribute"]
        return r["item_key"], r["attribute"]

    # ------------------------------------------------------------ parity
    conflict_keys = {oid: {q["item_key"] for q in gates[oid]["clarifications"] if q["rule"] in ("R3",)} for oid in offers}
    rows: dict[tuple[str, str], dict] = {}
    for oid in offers:
        for r in norm[oid]["records"]:
            if r["category"] not in TECH_CATEGORIES or r["scope_class"] in ("EXCLUDED", "BUYER_SUPPLY"):
                continue
            key = canon(oid, r)
            row = rows.setdefault(key, {"item_key": key[0], "attribute": key[1], "item": r["item"], "cells": {}})
            row["cells"].setdefault(oid, []).append(r)
    parity = []
    baselines = {(b["offer_id"], b["item_key"]): b for b in align["baselines"]}
    for key in sorted(rows):
        row = rows[key]
        out = {"item_key": row["item_key"], "attribute": row["attribute"], "item": row["item"], "offers": {}, "row_flags": []}
        units = set()
        for oid in offers:
            recs = row["cells"].get(oid, [])
            if not recs:
                out["offers"][oid] = {"value": None, "unit": None, "flags": ["NOT_STATED"], "finding_ids": [], "pages": []}
                continue
            recs.sort(key=lambda r: PREFERENCE.index(r["scope_class"]) if r["scope_class"] in PREFERENCE else 99)
            best = recs[0]
            flags = sorted({r["scope_class"] for r in recs} - {"BASE"})
            if row["item_key"] in conflict_keys[oid]:
                flags.append("CONFLICT")
            if any(r["verification"] == "VLM_ONLY" for r in recs):
                flags.append("VLM_ONLY")
            if len({str(r["si_value"]) for r in recs if r["si_value"] is not None and r["scope_class"] == best["scope_class"]}) > 1:
                flags.append("MULTI_VALUE")
            cell = {
                "value": best["si_value"],
                "unit": best["si_unit"],
                "raw": f"{best['raw_value']} {best['raw_unit'] or ''}".strip(),
                "flags": sorted(set(flags)),
                "finding_ids": [r["finding_id"] for r in recs],
                "pages": sorted({r["source_page"] for r in recs}),
            }
            if best["si_unit"]:
                units.add(best["si_unit"])
            out["offers"][oid] = cell
        if len(units) > 1:
            out["row_flags"].append("UNIT_MISMATCH_AFTER_NORMALIZATION")
        parity.append(out)

        # baseline per-tonne derivation
        unit = next(iter(units)) if len(units) == 1 else None
        if unit in PER_TONNE_UNITS:
            rates = {oid: (baselines.get((oid, row["item_key"])) or {}).get("reference_rate_kg_h") for oid in offers if oid in row["cells"]}
            if any(v is not None for v in rates.values()):
                pt = {"item_key": row["item_key"], "attribute": row["attribute"] + "@per_tonne", "item": row["item"] + " (per tonne, baseline-normalized)", "offers": {}, "row_flags": ["DERIVED_BY_BUILD_MATRIX"]}
                for oid in offers:
                    cell = out["offers"][oid]
                    rate = rates.get(oid)
                    if cell["value"] is None or not isinstance(cell["value"], (int, float)) or not rate:
                        pt["offers"][oid] = {"value": None, "unit": PER_TONNE_UNITS[unit], "flags": ["BASELINE_UNKNOWN"], "finding_ids": cell["finding_ids"], "pages": cell["pages"]}
                    else:
                        pt["offers"][oid] = {"value": round(cell["value"] / (rate / 1000.0), 4), "unit": PER_TONNE_UNITS[unit], "flags": [f"AT_{rate:g}_KG_H"], "finding_ids": cell["finding_ids"], "pages": cell["pages"]}
                distinct = {r for r in rates.values() if r}
                if len(distinct) > 1 or any(r is None for r in rates.values()):
                    out["row_flags"].append("BASELINE_MISMATCH")
                parity.append(pt)

    # ------------------------------------------------------------ landed cost
    head = {h["offer_id"]: h for h in align["headline_prices"]}
    landed = {}
    for oid in offers:
        lines = []
        unpriced = []
        h = head.get(oid)
        base = None
        if h and h["amount"] is not None:
            base = fx_convert(h["amount"], h["currency"], report_ccy, fx)
            if base is None:
                unpriced.append({"what": "headline price", "reason": f"no FX rate {h['currency']}->{report_ccy}"})
        else:
            unpriced.append({"what": "headline price", "reason": "not stated in offer or not extracted"})
        hrec = by_id.get(f"{(h or {}).get('finding_id')}@{oid}") or {}
        lines.append({"type": "HEADLINE", "label": "Headline price", "low": base, "high": base, "finding_id": (h or {}).get("finding_id"),
                      "basis": (h or {}).get("incoterm", ""), "page": hrec.get("source_page")})

        for mo in [m for m in align["mandatory_options"] if m["offer_id"] == oid]:
            r = by_id.get(mo["finding_id"] + "@" + oid)
            label = r["item"] if r else mo["finding_id"]
            price = (r or {}).get("option_price")
            if price:
                amt = fx_convert(price["amount"], price["currency"], report_ccy, fx)
                if amt is None:
                    unpriced.append({"what": label, "reason": f"no FX rate {price['currency']}->{report_ccy}", "finding_id": mo["finding_id"]})
                else:
                    lines.append({"type": "MANDATORY_OPTION", "label": label, "low": amt, "high": amt, "finding_id": mo["finding_id"], "basis": mo["reason"], "page": (r or {}).get("source_page")})
                    continue
            else:
                unpriced.append({"what": label, "reason": "option price not stated by vendor", "finding_id": mo["finding_id"], "page": (r or {}).get("source_page")})
            lines.append({"type": "MANDATORY_OPTION", "label": label, "low": None, "high": None, "finding_id": mo["finding_id"], "basis": mo["reason"], "page": (r or {}).get("source_page"), "unpriced": True})

        for ca in [c for c in align.get("cost_adders", []) if c["offer_id"] == oid]:
            r = by_id.get(ca["finding_id"] + "@" + oid)
            label = r["item"] if r else ca["cost_adder_key"]
            entry = ((cost_book or {}).get("items") or {}).get(ca["cost_adder_key"])
            lo = hi = None
            reason = None
            if not entry:
                reason = "no cost book entry" if cost_book else "no cost book supplied"
            elif entry.get("basis") == "per_unit":
                qty = ca.get("quantity", entry.get("default_quantity"))
                if qty is None or entry.get("low_per_unit") is None or entry.get("high_per_unit") is None:
                    reason = "cost book per-unit rate or quantity missing"
                else:
                    lo, hi = entry["low_per_unit"] * qty, entry["high_per_unit"] * qty
            else:
                if entry.get("low") is None or entry.get("high") is None:
                    reason = "cost book lump sum not filled"
                else:
                    lo, hi = entry["low"], entry["high"]
            if lo is not None:
                ccy = (cost_book or {}).get("currency", report_ccy)
                lo2, hi2 = fx_convert(lo, ccy, report_ccy, fx), fx_convert(hi, ccy, report_ccy, fx)
                if lo2 is None:
                    reason = f"no FX rate {ccy}->{report_ccy}"
                    lo = hi = None
                else:
                    lo, hi = lo2, hi2
            if reason:
                unpriced.append({"what": label, "reason": reason, "finding_id": ca["finding_id"], "cost_adder_key": ca["cost_adder_key"], "page": (r or {}).get("source_page")})
            lines.append({"type": "SCOPE_ADDER", "label": label, "low": lo, "high": hi, "finding_id": ca["finding_id"], "cost_adder_key": ca["cost_adder_key"],
                          "basis": (entry or {}).get("source", ""), "page": (r or {}).get("source_page"), "unpriced": reason is not None})

        priced = [ln for ln in lines if ln["low"] is not None]
        landed[oid] = {
            "vendor": norm[oid]["vendor"],
            "currency": report_ccy,
            "lines": lines,
            "total_low": round(sum(ln["low"] for ln in priced), 2) if priced else None,
            "total_high": round(sum(ln["high"] for ln in priced), 2) if priced else None,
            "headline": base,
            "unpriced": unpriced,
            "unpriced_count": len(unpriced),
            "complete": base is not None and not unpriced,
        }

    # ------------------------------------------------------------ branches
    branches = []
    for br in align["branches"]:
        oid = br["offer_id"]

        def describe(fids):
            out = []
            for fid in fids:
                r = by_id.get(fid + "@" + oid)
                if r:
                    out.append({"finding_id": fid, "item": r["item"], "page": r["source_page"], "price": r.get("option_price"), "status": r["status"]})
                else:
                    out.append({"finding_id": fid, "item": "UNKNOWN_FINDING", "page": None, "price": None, "status": None})
            return out

        base_items = describe(br["base_finding_ids"])
        alt_items = describe(br["alternative_finding_ids"])

        def total(items):
            vals = []
            for it in items:
                p = it["price"]
                if not p:
                    return None
                v = fx_convert(p["amount"], p["currency"], report_ccy, fx)
                if v is None:
                    return None
                vals.append(v)
            return round(sum(vals), 2)

        bt, at = total(base_items), total(alt_items)
        branches.append({
            "offer_id": oid, "group": br["group"], "base": base_items, "alternative": alt_items,
            "base_price": bt, "alternative_price": at,
            "delta_alternative_minus_base": round(at - bt, 2) if bt is not None and at is not None else None,
            "tradeoffs": br.get("tradeoffs", []), "recommended": br.get("recommended", "UNDECIDED"),
        })

    # ------------------------------------------------------------ dossier
    dossier = {oid: gates[oid]["clarifications"] for oid in offers}
    red_flags = {oid: gates[oid]["red_flags"] for oid in offers}

    matrix = {
        "project": state["project"],
        "report_currency": report_ccy,
        "offers": {oid: {"vendor": norm[oid]["vendor"], "gate_verdict": gates[oid]["verdict"]} for oid in offers},
        "parity": parity,
        "landed_cost": landed,
        "branches": branches,
        "dossier": dossier,
        "red_flags": red_flags,
        "notes": align.get("notes", []),
    }
    dump_json(comp / "matrix.json", matrix)

    with open(comp / "parity.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["item_key", "attribute", "item"] + [f"{o} value" for o in offers] + [f"{o} unit" for o in offers] + [f"{o} flags" for o in offers] + [f"{o} pages" for o in offers] + ["row_flags"])
        for r in parity:
            w.writerow([r["item_key"], r["attribute"], r["item"]]
                       + [r["offers"][o]["value"] for o in offers]
                       + [r["offers"][o]["unit"] for o in offers]
                       + [" ".join(r["offers"][o]["flags"]) for o in offers]
                       + [" ".join(map(str, r["offers"][o]["pages"])) for o in offers]
                       + [" ".join(r["row_flags"])])
    with open(comp / "landed_cost.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["offer_id", "type", "label", "low", "high", "currency", "finding_id", "page", "unpriced", "basis"])
        for oid, lc in landed.items():
            for ln in lc["lines"]:
                w.writerow([oid, ln["type"], ln["label"], ln["low"], ln["high"], report_ccy, ln.get("finding_id"), ln.get("page"), ln.get("unpriced", False), ln.get("basis", "")])
            w.writerow([oid, "TOTAL_PRICED", "", lc["total_low"], lc["total_high"], report_ccy, "", "", lc["unpriced_count"], ""])
    with open(comp / "branches.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["offer_id", "group", "base_items", "alternative_items", "base_price", "alternative_price", "delta", "recommended"])
        for b in branches:
            w.writerow([b["offer_id"], b["group"], " | ".join(i["item"] for i in b["base"]), " | ".join(i["item"] for i in b["alternative"]),
                        b["base_price"], b["alternative_price"], b["delta_alternative_minus_base"], b["recommended"]])
    with open(comp / "dossier.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["clarification_id", "offer_id", "priority", "category", "item", "question", "pages", "financial_impact"])
        for oid, qs in dossier.items():
            for q in qs:
                w.writerow([q["clarification_id"], oid, q["priority"], q["category"], q["item"], q["question"],
                            " ".join(str(e["page"]) for e in q["evidence"]), q["financial_impact"]])

    print(f"matrix: {len(parity)} parity rows, {len(branches)} branches, currency {report_ccy}")
    for oid, lc in landed.items():
        tl = "n/a" if lc["total_low"] is None else f"{lc['total_low']:,.0f}-{lc['total_high']:,.0f}"
        print(f"  {oid}: priced landed {tl} {report_ccy} | UNPRICED items: {lc['unpriced_count']} | clarifications: {len(dossier[oid])}")
    print(f"wrote {comp / 'matrix.json'} and CSV exports")


if __name__ == "__main__":
    main()
