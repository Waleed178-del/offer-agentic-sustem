#!/usr/bin/env python3
"""Phase 5: audit all 7 agents, then package the run into two zip files.

Nothing is generated unless every agent passes a fresh, read-only audit.

  ZIP 1  <project>_7_agent_outputs.zip
         The deliverables of all 7 agents, one folder per agent:
           Admin/                      report, RFQ dossiers, adjudication, gate verdicts, risk registers, state
           Agent_1_Ingestion/          document maps and vision transcriptions
           Agent_2_Press_Hydraulics/   payloads
           Agent_3_Thermal_Utilities/  payloads
           Agent_4_Downstream_Handling/ payloads
           Agent_5_Risk_RedTeam/       payloads
           Agent_6_Normalizer/         alignment, matrix, CSV exports
  ZIP 2  <project>_supporting_results.zip
         Every other file of the run (corpus, prescan, dispatch, validation,
         normalized data, inputs, loop orders) at its run-relative path.

Both zips carry AUDIT_MANIFEST.json: per-agent audit checks and the sha256
of every packaged file. Each zip is reopened and verified after writing.

Audit per agent (all must pass):
  global   phase is complete, source PDFs unchanged since init
  Agent 1  document map present, schema valid, transcriptions present,
           identical to what the gate audited
  Agent 2-5 payload present, schema valid, ids match, self-check honest,
           evidence re-verified against page text (only findings the gate
           already quarantined may fail), identical to what the gate audited
  Agent 6  alignment schema valid and covers every offer, matrix built from
           the current alignment, normalized data and gate reports
  Admin    every gate verdict passing, adjudication written, report rendered
           from the current matrix and adjudication, report files unchanged

Exit 0 packaged, 1 audit failed (no zips written), 2 usage error.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    AGENT_IDS,
    WORKER_FILES,
    die,
    dump_json,
    load_json,
    load_schema,
    sha256_file,
    validate_schema,
)
from validate_payload import CONTRADICTION, check_evidence  # noqa: E402

AGENT_FOLDERS = {
    "admin": "Admin",
    1: "Agent_1_Ingestion",
    2: "Agent_2_Press_Hydraulics",
    3: "Agent_3_Thermal_Utilities",
    4: "Agent_4_Downstream_Handling",
    5: "Agent_5_Risk_RedTeam",
    6: "Agent_6_Normalizer",
}
PASSING = ("PASS", "PASS_WITH_CLARIFICATIONS")


class Audit:
    def __init__(self) -> None:
        self.sections: dict[str, dict] = {}

    def check(self, agent: str, name: str, ok: bool, detail: str = "") -> bool:
        sec = self.sections.setdefault(agent, {"status": "PASS", "checks": []})
        sec["checks"].append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            sec["status"] = "FAIL"
        return ok

    def warn(self, agent: str, name: str, detail: str) -> None:
        sec = self.sections.setdefault(agent, {"status": "PASS", "checks": []})
        sec["checks"].append({"check": name, "result": "WARN", "detail": detail})

    @property
    def passed(self) -> bool:
        return all(s["status"] == "PASS" for s in self.sections.values())


def rel(run_dir: Path, p: Path) -> str:
    return p.resolve().relative_to(run_dir.resolve()).as_posix()


def hashes_match(run_dir: Path, recorded: dict[str, str] | None, must_include: list[Path]) -> tuple[bool, str]:
    """True when every recorded fingerprint still matches and every required file was recorded."""
    if not recorded:
        return False, "no recorded fingerprints (rerun the step that produced this file)"
    problems = []
    for p in must_include:
        if p.exists() and rel(run_dir, p) not in recorded:
            problems.append(f"{rel(run_dir, p)} was not part of the audited inputs")
    for rp, h in recorded.items():
        f = run_dir / rp
        if not f.exists():
            problems.append(f"{rp} missing")
        elif sha256_file(f) != h:
            problems.append(f"{rp} changed after it was audited")
    return not problems, "; ".join(problems[:6])


def audit_run(run_dir: Path, state: dict) -> tuple[Audit, dict[str, list[tuple[str, Path]]]]:
    au = Audit()
    offers = list(state["offers"])
    members: dict[str, list[tuple[str, Path]]] = {k: [] for k in AGENT_FOLDERS}

    # ---------------- global
    au.check("global", "phase is complete", state["phase"] in ("complete", "packaged"),
             f"phase={state['phase']}; finish Phase 4 and advance to complete first")
    for oid, o in state["offers"].items():
        pdf = Path(o["pdf_path"])
        if not pdf.exists():
            au.warn("global", f"{oid} source PDF", f"{pdf} not found; cannot re-confirm hash {o['sha256'][:12]}")
        else:
            au.check("global", f"{oid} source PDF unchanged", sha256_file(pdf) == o["sha256"], str(pdf))

    payload_schema = load_schema("worker_payload.schema.json")
    dm_schema = load_schema("document_map.schema.json")
    gates: dict[str, dict] = {}

    for oid in offers:
        odir = run_dir / oid
        gpath = odir / "gate" / "gate_report.json"
        gate = load_json(gpath) if gpath.exists() else None
        gates[oid] = gate or {}
        gate_inputs = (gate or {}).get("inputs_sha256")
        page_count = state["offers"][oid].get("page_count")

        # ---------------- Agent 1
        a1 = "Agent 1"
        dm_path = odir / "document_map.json"
        if au.check(a1, f"{oid} document map present", dm_path.exists(), rel(run_dir, dm_path) if dm_path.exists() else str(dm_path)):
            dm = load_json(dm_path)
            errs = validate_schema(dm, dm_schema)
            au.check(a1, f"{oid} document map schema", not errs, "; ".join(errs[:5]))
            if not errs:
                au.check(a1, f"{oid} document map offer id", dm["offer_id"] == oid, dm["offer_id"])
                missing = [d["transcription_file"] for d in dm["drawings"] if not (odir / d["transcription_file"]).exists()]
                au.check(a1, f"{oid} drawing transcriptions present", not missing, ", ".join(missing[:6]))
            ok, why = hashes_match(run_dir, {k: v for k, v in (gate_inputs or {}).items() if k.endswith("document_map.json")}, [dm_path])
            au.check(a1, f"{oid} document map identical to gated version", ok, why)
            members[1].append((f"{oid}/document_map.json", dm_path))
            for v in sorted((odir / "corpus" / "pages").glob("*.vlm.md")):
                members[1].append((f"{oid}/vision_transcriptions/{v.name}", v))

        # ---------------- Admin gate for this offer
        adm = "Admin"
        if au.check(adm, f"{oid} gate report present", gate is not None, str(gpath)):
            au.check(adm, f"{oid} gate verdict passing", gate["verdict"] in PASSING, f"verdict={gate['verdict']}")
            vpath = odir / "gate" / "validation.json"
            ok, why = hashes_match(run_dir, {k: v for k, v in (gate_inputs or {}).items() if k.endswith("validation.json")}, [vpath])
            au.check(adm, f"{oid} gate used current validation", ok, why)
            members["admin"].append((f"{oid}/gate_report.json", gpath))
            rr = odir / "gate" / "risk_register.json"
            if au.check(adm, f"{oid} risk register present", rr.exists(), str(rr)):
                members["admin"].append((f"{oid}/risk_register.json", rr))

        # ---------------- Agents 2 to 5
        quarantined = set((gate or {}).get("quarantined_finding_ids", []))
        loaded: dict[int, dict] = {}
        for num, fname in WORKER_FILES.items():
            ag = f"Agent {num}"
            ppath = odir / "payloads" / fname
            if not au.check(ag, f"{oid} payload present", ppath.exists(), str(ppath)):
                continue
            data = load_json(ppath)
            errs = validate_schema(data, payload_schema)
            if not au.check(ag, f"{oid} payload schema", not errs, "; ".join(errs[:5])):
                continue
            au.check(ag, f"{oid} agent and offer ids", data["agent_id"] == AGENT_IDS[num] and data["offer_id"] == oid,
                     f"{data['agent_id']} / {data['offer_id']}")
            bad_ids = [f["finding_id"] for f in data["extracted_findings"] if not f["finding_id"].startswith(f"A{num}-")]
            au.check(ag, f"{oid} finding id prefixes", not bad_ids, ", ".join(bad_ids[:6]))
            sc = data["self_check"]
            au.check(ag, f"{oid} self-check complete",
                     all(sc.get(k) for k in ("all_quotes_verbatim", "all_assigned_sections_read", "no_values_inferred_without_derivation")),
                     sc.get("notes", ""))
            ok, why = hashes_match(run_dir, {k: v for k, v in (gate_inputs or {}).items() if k.endswith(f"payloads/{fname}")}, [ppath])
            au.check(ag, f"{oid} payload identical to gated version", ok, why)
            loaded[num] = data
            members[num].append((f"{oid}/{fname}", ppath))

        all_ids = {f["finding_id"] for d in loaded.values() for f in d["extracted_findings"]}
        for num, data in loaded.items():
            ag = f"Agent {num}"
            failed = []
            for f in data["extracted_findings"]:
                checks = []
                if f["evidence_type"] == "DERIVED":
                    d = f.get("derivation") or {}
                    ok = bool(d) and bool(d.get("tool_output")) and all(i in all_ids for i in d.get("input_finding_ids", []))
                    checks.append(ok)
                elif f["category"] in CONTRADICTION or f["status"] == "CONFLICTING_SPECS":
                    sup = f.get("supporting_evidence", [])
                    checks.append(len(sup) >= 2)
                    checks += [check_evidence(odir, e["quote"], e["page"], e.get("evidence_type", "TEXT"), page_count)["status"] != "FAILED" for e in sup]
                else:
                    checks.append(check_evidence(odir, f["evidence_quote"], f["source_page"], f["evidence_type"], page_count)["status"] != "FAILED")
                    checks += [check_evidence(odir, e["quote"], e["page"], e.get("evidence_type", "TEXT"), page_count)["status"] != "FAILED"
                               for e in f.get("supporting_evidence", [])]
                if not all(checks):
                    failed.append(f["finding_id"])
            unaccepted = [x for x in failed if x not in quarantined]
            au.check(ag, f"{oid} evidence re-verified", not unaccepted,
                     f"unverified findings not quarantined by the gate: {', '.join(unaccepted[:8])}" if unaccepted
                     else (f"{len(failed)} quarantined finding(s) excluded from comparison: {', '.join(failed[:8])}" if failed else "all quotes found on cited pages"))

    # ---------------- Agent 6
    a6 = "Agent 6"
    comp = run_dir / "comparison"
    apath = comp / "alignment.json"
    if au.check(a6, "alignment present", apath.exists(), str(apath)):
        align = load_json(apath)
        errs = validate_schema(align, load_schema("alignment.schema.json"))
        au.check(a6, "alignment schema", not errs, "; ".join(errs[:5]))
        if not errs:
            au.check(a6, "alignment covers every offer", sorted(align["offers"]) == sorted(offers),
                     f"alignment={align['offers']} state={offers}")
        members[6].append(("alignment.json", apath))
    mpath = comp / "matrix.json"
    if au.check(a6, "matrix present", mpath.exists(), str(mpath)):
        matrix = load_json(mpath)
        req = [apath] + [run_dir / o / "normalized" / "offer_normalized.json" for o in offers] + [run_dir / o / "gate" / "gate_report.json" for o in offers]
        ok, why = hashes_match(run_dir, matrix.get("inputs_sha256"), req)
        au.check(a6, "matrix built from current inputs", ok, why)
        for o in offers:
            npath = run_dir / o / "normalized" / "offer_normalized.json"
            if au.check(a6, f"{o} normalized data present", npath.exists(), str(npath)):
                nrec = load_json(npath)
                ok, why = hashes_match(run_dir, nrec.get("inputs_sha256"), [run_dir / o / "gate" / "gate_report.json"])
                au.check(a6, f"{o} normalized from current gated payloads", ok, why)
        members[6].append(("matrix.json", mpath))
        for csvf in sorted(comp.glob("*.csv")):
            members[6].append((csvf.name, csvf))

    # ---------------- Admin report
    adm = "Admin"
    adj = comp / "admin_adjudication.md"
    if au.check(adm, "adjudication written", adj.exists() and adj.read_text(encoding="utf-8").strip() != "", str(adj)):
        members["admin"].append(("admin_adjudication.md", adj))
    rep = run_dir / "report"
    rman = rep / "report_manifest.json"
    if au.check(adm, "report rendered", rman.exists() and (rep / "Executive_Procurement_Report.md").exists(), str(rep)):
        man = load_json(rman)
        ok, why = hashes_match(run_dir, man.get("inputs_sha256"), [mpath, adj])
        au.check(adm, "report rendered from current matrix and adjudication", ok, why)
        ok, why = hashes_match(run_dir, man.get("outputs_sha256"), [rep / "Executive_Procurement_Report.md"])
        au.check(adm, "report files unchanged since rendering", ok, why)
        members["admin"].append(("report/Executive_Procurement_Report.md", rep / "Executive_Procurement_Report.md"))
        for r in sorted(rep.glob("RFQ_Clarifications_*.md")):
            members["admin"].append((f"report/{r.name}", r))
        members["admin"].append(("report/report_manifest.json", rman))
    members["admin"].append(("state.json", run_dir / "state.json"))
    return au, members


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "offer_audit"


def write_zip(path: Path, entries: list[tuple[str, Path]], manifest_bytes: bytes, extra: dict[str, bytes]) -> None:
    tmp = path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("AUDIT_MANIFEST.json", manifest_bytes)
        for name, data in extra.items():
            z.writestr(name, data)
        for arc, src in entries:
            z.write(src, arc)
    tmp.replace(path)


def verify_zip(path: Path, expected: dict[str, str]) -> list[str]:
    import hashlib

    problems = []
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            problems.append(f"corrupt member {bad}")
        names = set(z.namelist())
        for arc, h in expected.items():
            if arc not in names:
                problems.append(f"missing {arc}")
            elif hashlib.sha256(z.read(arc)).hexdigest() != h:
                problems.append(f"hash mismatch {arc}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--audit-only", action="store_true", help="run the audit and print it, write no zips")
    a = ap.parse_args()
    run_dir = Path(a.run_dir).resolve()
    if not (run_dir / "state.json").exists():
        die(f"{run_dir}/state.json not found")
    state = load_json(run_dir / "state.json")
    pkg = run_dir / "package"
    pkg.mkdir(exist_ok=True)

    au, members = audit_run(run_dir, state)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print(f"AUDIT {'PASSED' if au.passed else 'FAILED'} for {state['project']}")
    order = ["global", "Admin"] + [f"Agent {n}" for n in range(1, 7)]
    for sec in order:
        info = au.sections.get(sec)
        if not info:
            continue
        fails = [c for c in info["checks"] if c["result"] == "FAIL"]
        warns = [c for c in info["checks"] if c["result"] == "WARN"]
        print(f"  {sec:<8} {info['status']}  ({len(info['checks'])} checks, {len(fails)} failed, {len(warns)} warnings)")
        for c in fails + warns:
            print(f"      {c['result']}: {c['check']}: {c['detail']}")

    if not au.passed:
        dump_json(pkg / "audit_failed.json", {"at": now, "audit": au.sections})
        old = sorted(pkg.glob("*.zip"))
        print("NO ZIPS GENERATED. Fix the failed checks, rerun the producing step, then package again.")
        if old:
            print("WARNING: older zips in package/ reflect a previous audited state: " + ", ".join(p.name for p in old))
        sys.exit(1)
    if a.audit_only:
        print("audit-only: no zips written")
        return
    (pkg / "audit_failed.json").unlink(missing_ok=True)

    agent_entries: list[tuple[str, Path]] = []
    for key, folder in AGENT_FOLDERS.items():
        for arc, src in members[key]:
            agent_entries.append((f"{folder}/{arc}", src))
    in_zip1 = {src.resolve() for _, src in agent_entries}
    support_entries = []
    for f in sorted(run_dir.rglob("*")):
        if not f.is_file() or f.suffix == ".tmp" or pkg in f.parents:
            continue
        if f.resolve() in in_zip1:
            continue
        support_entries.append((rel(run_dir, f), f))

    base = slug(state["project"])
    zip1 = pkg / f"{base}_7_agent_outputs.zip"
    zip2 = pkg / f"{base}_supporting_results.zip"
    files1 = {arc: sha256_file(src) for arc, src in agent_entries}
    files2 = {arc: sha256_file(src) for arc, src in support_entries}
    per_agent = {AGENT_FOLDERS[k]: len(v) for k, v in members.items()}
    manifest = {
        "project": state["project"],
        "packaged_at": now,
        "audit_status": "PASS",
        "audit": au.sections,
        "offers": {oid: {"vendor": o["vendor"], "pdf_sha256": o["sha256"], "gate_verdict": o.get("gate_verdict")} for oid, o in state["offers"].items()},
        "zips": {
            zip1.name: {"purpose": "Deliverables of all 7 agents, one folder per agent", "files_per_agent": per_agent, "files": files1},
            zip2.name: {"purpose": "All other results of the run (corpus, prescan, dispatch, validation, normalized data, inputs)", "files": files2},
        },
    }
    import json

    mbytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    readme = (
        f"{state['project']}: offer audit package\n\n"
        f"Packaged {now} after a passing audit of all 7 agents (see AUDIT_MANIFEST.json).\n\n"
        "Start with Admin/report/Executive_Procurement_Report.md.\n"
        "Vendor questions: Admin/report/RFQ_Clarifications_<OFFER>.md.\n\n"
        "Folders:\n" + "\n".join(f"  {AGENT_FOLDERS[k]}/  ({n} files)" for k, n in ((k, len(v)) for k, v in members.items())) + "\n\n"
        f"Supporting files are in {zip2.name}.\n"
    ).encode("utf-8")
    write_zip(zip1, agent_entries, mbytes, {"README.txt": readme})
    write_zip(zip2, support_entries, mbytes, {})

    problems = verify_zip(zip1, files1) + verify_zip(zip2, files2)
    if problems:
        zip1.unlink(missing_ok=True)
        zip2.unlink(missing_ok=True)
        die("zip verification failed, zips removed: " + "; ".join(problems[:10]), code=1)

    dump_json(pkg / "AUDIT_MANIFEST.json", manifest)
    state = load_json(run_dir / "state.json")
    state["package"] = {"at": now, "agent_zip": str(zip1), "supporting_zip": str(zip2)}
    if state["phase"] == "complete":
        state["phase"] = "packaged"
        state.setdefault("history", []).append({"phase": "packaged", "at": now})
    dump_json(run_dir / "state.json", state)

    print(f"ZIP 1 {zip1}  ({len(files1)} files, {zip1.stat().st_size:,} bytes)")
    for folder, n in per_agent.items():
        print(f"        {folder}: {n} files")
    print(f"ZIP 2 {zip2}  ({len(files2)} files, {zip2.stat().st_size:,} bytes)")
    print("Both zips reopened and verified against AUDIT_MANIFEST.json.")


if __name__ == "__main__":
    main()
