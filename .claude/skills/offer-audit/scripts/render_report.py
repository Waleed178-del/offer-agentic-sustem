#!/usr/bin/env python3
"""Render the Final Executive Procurement Report from comparison/matrix.json.

Writes RUN_DIR/report/Executive_Procurement_Report.md and one vendor-ready
RFQ dossier per offer: RUN_DIR/report/RFQ_Clarifications_<OFFER>.md.
Embeds comparison/admin_adjudication.md when present.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import die, load_json  # noqa: E402


def fmt(v, unit: str | None = None) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        s = f"{v:,.3f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}"
    else:
        s = str(v)
    return f"{s} {unit}".strip() if unit and unit != "text" else s


def money(v, ccy) -> str:
    return "UNPRICED" if v is None else f"{v:,.0f} {ccy}"


def esc(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    a = ap.parse_args()
    run_dir = Path(a.run_dir).resolve()
    mpath = run_dir / "comparison" / "matrix.json"
    if not mpath.exists():
        die("comparison/matrix.json missing. Run build_matrix.py first.")
    m = load_json(mpath)
    offers = list(m["offers"])
    ccy = m["report_currency"]
    out: list[str] = []
    w = out.append

    w(f"# Executive Procurement Report: {m['project']}")
    w("")
    w(f"Generated {date.today().isoformat()} by the offer-audit 7-agent system. Every figure traces to a page-cited, machine-verified finding. Report currency {ccy}.")
    w("")
    w("| Offer | Vendor | Gate verdict | Priced landed cost | Unpriced items | Open clarifications | Red flags |")
    w("|---|---|---|---|---|---|---|")
    for oid in offers:
        lc = m["landed_cost"][oid]
        rng = "—" if lc["total_low"] is None else (money(lc["total_low"], ccy) if lc["total_low"] == lc["total_high"] else f"{money(lc['total_low'], ccy)} to {money(lc['total_high'], ccy)}")
        w(f"| {oid} | {esc(m['offers'][oid]['vendor'])} | {m['offers'][oid]['gate_verdict']} | {rng} | {lc['unpriced_count']} | {len(m['dossier'][oid])} | {len(m['red_flags'][oid])} |")
    w("")
    w("> Landed cost is a floor while any item is UNPRICED. Do not rank offers on price until the unpriced count is zero or bounded by a cost book entry.")
    w("")

    adj = run_dir / "comparison" / "admin_adjudication.md"
    if adj.exists():
        w("## Admin Adjudication")
        w("")
        w(adj.read_text(encoding="utf-8").strip())
        w("")

    # View 1
    w("## View 1: System-by-System Technical Parity")
    w("")
    w("Values in SI baseline units. Flags: OPTION, ALTERNATIVE, DERIVED, MISSING, CONFLICT, CORRUPTED, VLM_ONLY (read from drawing), BASE_PRELIMINARY, NOT_STATED.")
    w("")
    w("| Item | Attribute | " + " | ".join(offers) + " | Row flags |")
    w("|---|---|" + "---|" * len(offers) + "---|")
    last_sys = None
    for r in m["parity"]:
        sys_name = r["item_key"].split(".")[0]
        if sys_name != last_sys:
            w(f"| **{esc(sys_name.upper())}** | |" + " |" * len(offers) + " |")
            last_sys = sys_name
        cells = []
        for oid in offers:
            c = r["offers"][oid]
            txt = fmt(c["value"], c["unit"])
            if c["flags"]:
                txt += " `" + " ".join(c["flags"]) + "`"
            if c["pages"]:
                txt += f" (p.{','.join(map(str, c['pages'][:4]))})"
            cells.append(esc(txt))
        w(f"| {esc(r['item'])} | {esc(r['attribute'])} | " + " | ".join(cells) + f" | {' '.join(r['row_flags'])} |")
    w("")

    # View 2
    w("## View 2: True Landed Cost Normalization")
    w("")
    for oid in offers:
        lc = m["landed_cost"][oid]
        w(f"### {oid} ({esc(lc['vendor'])})")
        w("")
        w("| Type | Line | Low | High | Page | Basis |")
        w("|---|---|---|---|---|---|")
        for ln in lc["lines"]:
            w(f"| {ln['type']} | {esc(ln['label'])} | {money(ln['low'], ccy)} | {money(ln['high'], ccy)} | {ln.get('page') or ''} | {esc(ln.get('basis') or '')} |")
        w(f"| **TOTAL (priced lines only)** | | **{money(lc['total_low'], ccy)}** | **{money(lc['total_high'], ccy)}** | | |")
        w("")
        if lc["unpriced"]:
            w(f"Unpriced ({lc['unpriced_count']}):")
            for u in lc["unpriced"]:
                pg = f" (p.{u['page']})" if u.get("page") else ""
                w(f"* {esc(u['what'])}{pg}: {esc(u['reason'])}")
            w("")

    # View 3
    w("## View 3: Configuration Branch Analysis")
    w("")
    if not m["branches"]:
        w("No base vs alternative branches identified.")
        w("")
    for b in m["branches"]:
        w(f"### {b['offer_id']}: {esc(b['group'])}")
        w("")
        w(f"* Base: " + "; ".join(f"{esc(i['item'])} (p.{i['page']})" for i in b["base"]))
        w(f"* Alternative: " + "; ".join(f"{esc(i['item'])} (p.{i['page']})" for i in b["alternative"]))
        w(f"* Price base / alternative / delta: {money(b['base_price'], ccy)} / {money(b['alternative_price'], ccy)} / {money(b['delta_alternative_minus_base'], ccy)}")
        for t in b["tradeoffs"]:
            w(f"  * {esc(t)}")
        w(f"* Recommended: **{b['recommended']}**")
        w("")

    # View 4
    w("## View 4: RFQ Clarification and Red-Flag Dossier")
    w("")
    for oid in offers:
        w(f"### {oid} ({esc(m['offers'][oid]['vendor'])})")
        w("")
        if m["red_flags"][oid]:
            w("**Scope blur red flags (promise vs bill of materials):**")
            for f in m["red_flags"][oid]:
                w(f"* {esc(f['item'])}: promised p.{f['promise']['page']} \"{esc(f['promise']['quote'][:180])}\" but {f['contradicting_scope']['status']} p.{f['contradicting_scope']['page']} \"{esc(f['contradicting_scope']['quote'][:180])}\"")
            w("")
        w("| ID | Priority | Category | Item | Question | Pages | Impact |")
        w("|---|---|---|---|---|---|---|")
        for q in m["dossier"][oid]:
            pages = ", ".join(str(e["page"]) for e in q["evidence"])
            w(f"| {q['clarification_id']} | {q['priority']} | {q['category']} | {esc(q['item'])} | {esc(q['question'])} | {pages} | {q['financial_impact']} |")
        w("")
    if m.get("notes"):
        w("## Normalization Notes (Agent 6)")
        w("")
        for n in m["notes"]:
            w(f"* {esc(n)}")
        w("")

    rep = run_dir / "report"
    rep.mkdir(exist_ok=True)
    (rep / "Executive_Procurement_Report.md").write_text("\n".join(out) + "\n", encoding="utf-8")

    for oid in offers:
        lines = [f"# Technical and Commercial Clarifications: {m['offers'][oid]['vendor']}", "",
                 f"Project: {m['project']}. Offer reference: {oid}. Please answer each item in writing, citing the revised page or annex. Items marked P1 must be resolved before contract signature.", ""]
        for q in m["dossier"][oid]:
            lines.append(f"## {q['clarification_id']} [{q['priority']}] {q['item']}")
            lines.append("")
            lines.append(q["question"])
            lines.append("")
            for e in q["evidence"]:
                lines.append(f"> Page {e['page']}: \"{e['quote']}\"")
            lines.append("")
        (rep / f"RFQ_Clarifications_{oid}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {rep / 'Executive_Procurement_Report.md'} and {len(offers)} RFQ dossiers")


if __name__ == "__main__":
    main()
