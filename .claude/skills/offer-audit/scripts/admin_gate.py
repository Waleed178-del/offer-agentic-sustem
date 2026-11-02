#!/usr/bin/env python3
"""Admin gatekeeping for one offer (Phase 3). Deterministic rules R1 to R7.

Inputs:  document_map.json, dispatch/agent_N.json, payloads/agent_N.json,
         gate/validation.json (run validate_payload.py first)
Outputs: gate/gate_report.json      verdict, rule results, clarifications
         gate/risk_register.json    every verified scope, risk and gap finding
         gate/loop_orders/agent_N.json   rework orders for workers to loop

Verdicts
  LOOP                       at least one worker must rework, budget remains
  PASS_WITH_CLARIFICATIONS   clean enough to compare, vendor questions open
  PASS                       nothing open
--finalize converts every remaining loop order into a vendor clarification.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENT_NUM_BY_ID, dump_json, iter_payloads, load_json, offer_dir, to_number  # noqa: E402
from normalize_units import UnitError, to_si  # noqa: E402

KEY_OWNER = [
    (("press.", "feeding.", "hydraulics.", "tooling.", "container.", "billet_shear.", "log_shear."), 2),
    (("utilities.", "furnace.", "quench.", "ageing_oven.", "die_oven.", "combustion.", "cooling_water."), 3),
    (("handling.", "puller.", "saw.", "stretcher.", "cooling_table.", "conveyor.", "runout.", "basket.", "stacker."), 4),
]
GAP_STATUSES = {"MISSING_DATA"}
SCOPE_NEG = {"OPTIONAL", "EXCLUDED_FROM_SUPPLY", "BUYER_SUPPLY"}
RISK_STATUSES = {"OPTIONAL", "EXCLUDED_FROM_SUPPLY", "BUYER_SUPPLY", "PRELIMINARY", "CONFLICTING_SPECS",
                 "MISSING_DATA", "CORRUPTED_VALUE", "ALTERNATIVE", "NOT_DERIVABLE", "DERIVED_ESTIMATE"}
RISK_CATEGORIES = {"HIDDEN_CAPEX_EXCLUSION", "BUYER_SUPPLY", "OPTIONAL_ITEM", "SCOPE_PROMISE", "TECHNICAL_CONTRADICTION",
                   "INCOMPLETE_SPECIFICATION", "DATA_CORRUPTION", "COMMERCIAL_TERM", "PERFORMANCE_GUARANTEE"}
NO_COMPARE_STATUSES = {"OPTIONAL", "ALTERNATIVE", "DERIVED_ESTIMATE", "MISSING_DATA", "NOT_DERIVABLE", "CORRUPTED_VALUE", "CONFLICTING_SPECS"}
IMPACT_RANK = {"HIGH": 0, "MEDIUM": 1, "UNKNOWN": 2, "LOW": 3, "NONE": 4}


def owner_of(item_key: str) -> int:
    for prefixes, agent in KEY_OWNER:
        if item_key.startswith(prefixes):
            return agent
    return 5


def comparable(f: dict):
    """Return a comparable value: rounded SI float or normalized string."""
    v = f.get("value")
    if v is None:
        return None
    num = to_number(v)
    if num is not None and f.get("unit"):
        try:
            si = to_si(num, f["unit"])
            return ("num", si["unit"], si["value"])
        except UnitError:
            return ("num", f["unit"].strip().lower(), num)
    if num is not None:
        return ("num", "", num)
    return ("str", "", " ".join(str(v).lower().split()))


def differs(a, b) -> bool:
    """True when two comparable values disagree. Mixed kinds or unit
    dimensions are not comparable and never raise a contradiction."""
    if a[0] != b[0]:
        return False
    if a[0] == "str":
        return a[2] != b[2]
    if a[1] != b[1]:
        return False
    hi = max(abs(a[2]), abs(b[2]), 1e-12)
    return abs(a[2] - b[2]) / hi > 0.01


def worst_impact(*impacts: str) -> str:
    return min(impacts, key=lambda x: IMPACT_RANK.get(x, 2))


def prio(impact: str, forced: str | None = None) -> str:
    if forced:
        return forced
    return {"HIGH": "P1", "MEDIUM": "P2"}.get(impact, "P3")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--offer", required=True)
    ap.add_argument("--finalize", action="store_true", help="convert all remaining loop orders into clarifications")
    a = ap.parse_args()
    run_dir = Path(a.run_dir).resolve()
    odir = offer_dir(run_dir, a.offer)
    state = load_json(run_dir / "state.json")
    max_loops = state.get("max_loops_per_agent", 2)
    loops_used = state["offers"][a.offer]["loops"]
    validation_path = odir / "gate" / "validation.json"
    if not validation_path.exists():
        print("ERROR: run validate_payload.py first", file=sys.stderr)
        sys.exit(2)
    validation = load_json(validation_path)
    dm = load_json(odir / "document_map.json")

    payloads: dict[int, dict] = {}
    for num, path in iter_payloads(odir):
        payloads[num] = load_json(path)

    loop_orders: dict[int, list[dict]] = {n: [] for n in (2, 3, 4, 5)}
    clar: list[dict] = []
    red_flags: list[dict] = []
    rules: dict[str, dict] = {}

    def add_clar(category, item, item_key, question, evidence, findings, impact, priority=None, rule=""):
        clar.append({
            "clarification_id": f"Q-{len(clar) + 1:03d}",
            "priority": prio(impact, priority),
            "rule": rule,
            "category": category,
            "item": item,
            "item_key": item_key,
            "question": question,
            "evidence": evidence,
            "source_findings": findings,
            "financial_impact": impact,
        })

    # ---- R1 schema
    r1 = []
    for num in (2, 3, 4, 5):
        info = validation["agents"].get(str(num))
        if info is None:
            r1.append(f"agent_{num}: payload missing")
            loop_orders[num].append({"rule": "R1", "order": "Payload file missing. Produce payloads/agent_%d.json per the data contract." % num})
        elif info["schema_errors"]:
            r1.append(f"agent_{num}: {len(info['schema_errors'])} schema errors")
            loop_orders[num].append({"rule": "R1", "order": "Fix schema errors and rewrite the full payload.", "errors": info["schema_errors"][:30]})
    rules["R1_schema"] = {"violations": r1}

    # verified findings only from here
    findings: dict[str, dict] = {}
    for num, p in payloads.items():
        if validation["agents"].get(str(num), {}).get("schema_errors"):
            continue
        for f in p["extracted_findings"]:
            v = validation["findings"].get(f["finding_id"], {}).get("verdict", "FAILED")
            f = dict(f, _agent=num, _verdict=v)
            findings[f["finding_id"]] = f

    # ---- R2 evidence
    r2 = []
    for fid, f in findings.items():
        if f["_verdict"] == "FAILED":
            reasons = [c.get("reason", "") for c in validation["findings"][fid]["checks"] if c["status"] == "FAILED"]
            r2.append(fid)
            loop_orders[f["_agent"]].append({"rule": "R2", "finding_id": fid, "order": "Evidence failed verification. Re-read the cited page, quote verbatim, fix page number, or delete the finding.", "reasons": reasons})
    rules["R2_evidence"] = {"quarantined": r2}
    good = {fid: f for fid, f in findings.items() if f["_verdict"] != "FAILED"}

    # ---- R3 contradictions
    r3 = []
    for fid, f in good.items():
        if f["status"] == "CONFLICTING_SPECS" or f["category"] == "TECHNICAL_CONTRADICTION":
            ev = [{"page": e["page"], "quote": e["quote"]} for e in f.get("supporting_evidence", [])]
            add_clar("TECHNICAL_CONTRADICTION", f["item"], f["item_key"],
                     f"The offer states conflicting specifications for {f['item']}. Confirm the binding specification in writing. {f['action_required']}",
                     ev, [fid], f["financial_impact"], rule="R3")
            r3.append({"type": "declared", "finding": fid})
    groups: dict[tuple, list[dict]] = {}
    for fid, f in good.items():
        if f["status"] in NO_COMPARE_STATUSES or f["evidence_type"] == "DERIVED":
            continue
        cv = comparable(f)
        if cv is None:
            continue
        groups.setdefault((f["item_key"], f.get("attribute") or "value"), []).append((f, cv))
    for (key, attr), items in groups.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                fa, ca = items[i]
                fb, cb = items[j]
                if not differs(ca, cb):
                    continue
                pair = [fa["finding_id"], fb["finding_id"]]
                cross_agent = fa["_agent"] != fb["_agent"]
                agents = {fa["_agent"], fb["_agent"]}
                budget_left = all(loops_used.get(str(n), 0) < 1 for n in agents)
                ev = [{"page": fa["source_page"], "quote": fa["evidence_quote"]}, {"page": fb["source_page"], "quote": fb["evidence_quote"]}]
                if cross_agent and budget_left and not a.finalize:
                    for n in agents:
                        loop_orders[n].append({"rule": "R3", "order": f"Cross-agent value conflict on {key}.{attr}: {fa['value']} {fa.get('unit') or ''} (p.{fa['source_page']}) vs {fb['value']} {fb.get('unit') or ''} (p.{fb['source_page']}). Re-read both pages. If the document itself is inconsistent, emit a TECHNICAL_CONTRADICTION finding with both quotes in supporting_evidence.", "findings": pair})
                    r3.append({"type": "cross_agent_reverify", "key": key, "attribute": attr, "findings": pair})
                else:
                    add_clar("TECHNICAL_CONTRADICTION", fa["item"], key,
                             f"Conflicting values for {fa['item']} ({attr}): {fa['value']} {fa.get('unit') or ''} on page {fa['source_page']} vs {fb['value']} {fb.get('unit') or ''} on page {fb['source_page']}. Which value is contractually binding?",
                             ev, pair, worst_impact(fa["financial_impact"], fb["financial_impact"]), rule="R3")
                    r3.append({"type": "value_conflict", "key": key, "attribute": attr, "findings": pair})
    rules["R3_contradiction"] = {"events": r3}

    # ---- R4 missing data
    r4 = []
    companions = {}
    for f in good.values():
        if f["status"] in ("DERIVED_ESTIMATE", "NOT_DERIVABLE"):
            companions.setdefault((f["item_key"], f.get("attribute") or "value"), []).append(f["finding_id"])
    for fid, f in good.items():
        if f["status"] not in GAP_STATUSES:
            continue
        k = (f["item_key"], f.get("attribute") or "value")
        add_clar("INCOMPLETE_SPECIFICATION", f["item"], f["item_key"],
                 f"Required data is blank or missing: {f['item']}{' / ' + f['attribute'] if f.get('attribute') else ''} (page {f['source_page']}). Populate with guaranteed values.",
                 [{"page": f["source_page"], "quote": f["evidence_quote"]}], [fid] + companions.get(k, []), f["financial_impact"], rule="R4")
        if k not in companions:
            owner = owner_of(f["item_key"])
            if owner == 5:
                owner = 3 if f["category"] == "UTILITY_CONSUMPTION" else owner
            loop_orders[owner].append({"rule": "R4", "finding_id": fid, "order": f"MISSING_DATA on {k[0]}.{k[1]}. Compute a bottom-up estimate from sub-equipment findings using normalize_units.py sum/per-tonne and emit a DERIVED_ESTIMATE finding with the same item_key and attribute, derivation.input_finding_ids, and tool_output. If no inputs exist, emit NOT_DERIVABLE with the reason."})
            r4.append({"finding": fid, "loop_owner": owner})
        else:
            r4.append({"finding": fid, "resolved_by": companions[k]})
    rules["R4_missing_data"] = {"events": r4}

    # ---- R5 scope blur
    r5 = []
    promises = [f for f in good.values() if f["category"] == "SCOPE_PROMISE"]
    negs = [f for f in good.values() if f["status"] in SCOPE_NEG]
    for p in promises:
        for n in negs:
            pk, nk = p["item_key"], n["item_key"]
            pa, na = p.get("attribute"), n.get("attribute")
            if pa and na and pa.strip().lower() != na.strip().lower():
                continue
            if pk == nk or pk.startswith(nk + ".") or nk.startswith(pk + "."):
                flag = {
                    "flag": "SCOPE_BLUR",
                    "item": p["item"],
                    "item_key": pk,
                    "promise": {"page": p["source_page"], "quote": p["evidence_quote"], "finding_id": p["finding_id"]},
                    "contradicting_scope": {"page": n["source_page"], "quote": n["evidence_quote"], "status": n["status"], "finding_id": n["finding_id"]},
                }
                red_flags.append(flag)
                add_clar("SCOPE_BLUR", p["item"], pk,
                         f"The offer promises {p['item']} (page {p['source_page']}) but lists it as {n['status']} (page {n['source_page']}). Confirm it is included in the base price, or quote it as a firm adder.",
                         [flag["promise"], flag["contradicting_scope"]], [p["finding_id"], n["finding_id"]], "HIGH", priority="P1", rule="R5")
                r5.append([p["finding_id"], n["finding_id"]])
    rules["R5_scope_blur"] = {"pairs": r5}

    # ---- R6 coverage
    r6 = []
    for num in (2, 3, 4, 5):
        dpath = odir / "dispatch" / f"agent_{num}.json"
        if not dpath.exists() or num not in payloads:
            continue
        req = set(load_json(dpath).get("required_section_ids", []))
        got = set(payloads[num].get("sections_covered", []))
        missing = sorted(req - got)
        if missing:
            r6.append({"agent": num, "missing_sections": missing})
            loop_orders[num].append({"rule": "R6", "order": "Assigned sections not covered. Read them and add findings, or list them in sections_covered with a self_check note if they hold nothing in your domain.", "sections": missing})
    rules["R6_coverage"] = {"gaps": r6}

    # ---- R7 corruption acknowledgement
    r7 = []
    acked = set()
    for p in payloads.values():
        acked.update(p.get("acknowledged_corruptions", []))
    for c in dm["data_corruption"]:
        if c["corruption_id"] in acked:
            continue
        owner = 5
        for num in (2, 3, 4):
            dpath = odir / "dispatch" / f"agent_{num}.json"
            if dpath.exists() and any(x["corruption_id"] == c["corruption_id"] for x in load_json(dpath).get("corruption", [])):
                owner = num
                break
        r7.append({"corruption_id": c["corruption_id"], "owner": owner})
        loop_orders[owner].append({"rule": "R7", "order": f"Corrupted cell {c['token']} on page {c['page']} ({c['context']}) not acknowledged. Recover the value from the metric column, drawings or other pages and emit a finding, or emit CORRUPTED_VALUE. Add {c['corruption_id']} to acknowledged_corruptions.", "corruption_id": c["corruption_id"]})
    rules["R7_corruption"] = {"unacknowledged": r7}

    # ---- vendor-facing gaps from statuses
    covered_fids = {fid for q in clar for fid in q["source_findings"]}
    for fid, f in good.items():
        if fid in covered_fids:
            continue
        if f["status"] in ("PRELIMINARY", "CORRUPTED_VALUE", "NOT_DERIVABLE"):
            add_clar(f["category"], f["item"], f["item_key"], f["action_required"],
                     [{"page": f["source_page"], "quote": f["evidence_quote"]}], [fid], f["financial_impact"], rule="STATUS")
        elif f["status"] in ("EXCLUDED_FROM_SUPPLY", "BUYER_SUPPLY") and f["financial_impact"] in ("HIGH", "MEDIUM"):
            add_clar(f["category"], f["item"], f["item_key"],
                     f"{f['item']} is {f['status'].replace('_', ' ').lower()}. Quote it as a firm turnkey adder or confirm interface responsibilities. {f['action_required']}",
                     [{"page": f["source_page"], "quote": f["evidence_quote"]}], [fid], f["financial_impact"], rule="STATUS")

    # ---- loop budget handling
    final_orders: dict[int, list[dict]] = {}
    for num, orders in loop_orders.items():
        if not orders:
            continue
        spent = loops_used.get(str(num), 0) >= max_loops
        if a.finalize or spent:
            for o in orders:
                add_clar("UNRESOLVED_AFTER_LOOP_BUDGET", o.get("rule", ""), "", f"Audit could not close: {o['order']}",
                         [], [o.get("finding_id")] if o.get("finding_id") else [], "UNKNOWN", priority="P2", rule=o.get("rule", ""))
        else:
            final_orders[num] = orders

    lo_dir = odir / "gate" / "loop_orders"
    lo_dir.mkdir(parents=True, exist_ok=True)
    for old in lo_dir.glob("agent_*.json"):
        old.unlink()
    for num, orders in final_orders.items():
        dump_json(lo_dir / f"agent_{num}.json", {
            "offer_id": a.offer, "agent": num, "loop_iteration": loops_used.get(str(num), 0) + 1,
            "payload": str(odir / "payloads" / f"agent_{num}.json"),
            "dispatch": str(odir / "dispatch" / f"agent_{num}.json"),
            "instruction": "Apply every order below, keep all valid findings, rewrite the full payload, set loop_iteration.",
            "orders": orders,
        })

    if final_orders:
        verdict = "LOOP"
    elif clar or red_flags:
        verdict = "PASS_WITH_CLARIFICATIONS"
    else:
        verdict = "PASS"

    clar.sort(key=lambda q: (q["priority"], IMPACT_RANK.get(q["financial_impact"], 2)))
    for i, q in enumerate(clar, start=1):
        q["clarification_id"] = f"{a.offer}-Q{i:03d}"

    risk = []
    for fid, f in sorted(good.items()):
        if f["status"] in RISK_STATUSES or f["category"] in RISK_CATEGORIES:
            risk.append({k: v for k, v in f.items() if not k.startswith("_")} | {"agent": f["_agent"], "verification": f["_verdict"]})
    risk.sort(key=lambda r: IMPACT_RANK.get(r["financial_impact"], 2))

    report = {
        "offer_id": a.offer,
        "vendor": state["offers"][a.offer]["vendor"],
        "verdict": verdict,
        "finalized": a.finalize,
        "loops_used": loops_used,
        "rules": rules,
        "loop_orders": {str(k): len(v) for k, v in final_orders.items()},
        "red_flags": red_flags,
        "clarifications": clar,
        "verified_finding_count": len(good),
        "quarantined_finding_count": len(r2),
    }
    dump_json(odir / "gate" / "gate_report.json", report)
    dump_json(odir / "gate" / "risk_register.json", {"offer_id": a.offer, "entries": risk})
    state["offers"][a.offer]["gate_verdict"] = verdict
    dump_json(run_dir / "state.json", state)

    print(f"{a.offer}: verdict={verdict} | verified={len(good)} quarantined={len(r2)} | clarifications={len(clar)} red_flags={len(red_flags)}")
    for name, res in rules.items():
        n = sum(len(v) for v in res.values())
        print(f"  {name}: {n}")
    for num, orders in final_orders.items():
        print(f"  LOOP agent_{num}: {len(orders)} orders -> {lo_dir / f'agent_{num}.json'}")


if __name__ == "__main__":
    main()
