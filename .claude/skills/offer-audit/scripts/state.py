#!/usr/bin/env python3
"""Run state machine for the Admin orchestrator.

Phases advance strictly in order:
  initialized -> ingestion_complete -> extraction_complete
  -> validation_complete -> normalization_complete -> complete

Commands
  init     create RUN_DIR, register offers, copy cost book and requirements
  status   print the current phase, loop counters and the next action
  advance  move to the next phase (refuses to skip phases)
  loop     record one rework loop for an agent on an offer, enforces budget
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import die, dump_json, load_json  # noqa: E402

PHASES = [
    "initialized",
    "ingestion_complete",
    "extraction_complete",
    "validation_complete",
    "normalization_complete",
    "complete",
]
MAX_LOOPS = 2

NEXT_ACTION = {
    "initialized": "Phase 1: run prescan.py per offer, dispatch Agent 1 per offer in parallel, validate document maps.",
    "ingestion_complete": "Phase 2: run route_sections.py per offer, dispatch Agents 2-5 for all offers in one parallel message.",
    "extraction_complete": "Phase 3: run validate_payload.py and admin_gate.py per offer, loop workers named in loop_orders.",
    "validation_complete": "Phase 4: run normalize_offer.py per offer, dispatch Agent 6, then build_matrix.py.",
    "normalization_complete": "Phase 4 close: write admin_adjudication.md, run render_report.py.",
    "complete": "Done. Report is in RUN_DIR/report/.",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pdf_pages(path: Path) -> int | None:
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
        for line in out.splitlines():
            if line.startswith("Pages:"):
                return int(line.split()[1])
    except (OSError, subprocess.CalledProcessError, ValueError):
        pass
    try:
        from pypdf import PdfReader  # type: ignore

        return len(PdfReader(str(path)).pages)
    except Exception:  # noqa: BLE001
        return None


def parse_offer(spec: str) -> tuple[str, Path, str]:
    # OFFER_ID=/path/file.pdf:Vendor Name
    if "=" not in spec:
        die(f"bad --offer {spec!r}; expected OFFER_ID=/path.pdf:Vendor")
    oid, rest = spec.split("=", 1)
    vendor = ""
    if ":" in rest and not rest.lower().endswith(".pdf"):
        path_s, vendor = rest.rsplit(":", 1)
    else:
        path_s = rest
    oid = oid.strip()
    if not oid or not oid.replace("_", "").isalnum():
        die(f"offer id {oid!r} must be alphanumeric with underscores")
    return oid, Path(path_s).expanduser().resolve(), vendor.strip() or oid


def cmd_init(a: argparse.Namespace) -> None:
    run_dir = Path(a.run_dir).resolve()
    if (run_dir / "state.json").exists() and not a.force:
        die(f"{run_dir}/state.json exists. Use status, or --force to reinitialise.")
    run_dir.mkdir(parents=True, exist_ok=True)
    offers = {}
    for spec in a.offer:
        oid, pdf, vendor = parse_offer(spec)
        if not pdf.is_file():
            die(f"offer PDF not found: {pdf}")
        odir = run_dir / oid
        for sub in ("corpus/pages", "corpus/images", "dispatch", "payloads", "gate/loop_orders", "normalized"):
            (odir / sub).mkdir(parents=True, exist_ok=True)
        offers[oid] = {
            "vendor": vendor,
            "pdf_path": str(pdf),
            "sha256": sha256(pdf),
            "page_count": pdf_pages(pdf),
            "loops": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
            "gate_verdict": None,
        }
    inputs = {}
    for label, src in (("cost_book", a.cost_book), ("requirements", a.requirements)):
        if src:
            s = Path(src).expanduser().resolve()
            if not s.is_file():
                die(f"{label} not found: {s}")
            dst = run_dir / "inputs" / s.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, dst)
            inputs[label] = str(dst)
    (run_dir / "comparison").mkdir(exist_ok=True)
    (run_dir / "report").mkdir(exist_ok=True)
    state = {
        "project": a.project,
        "created_at": now(),
        "phase": "initialized",
        "history": [{"phase": "initialized", "at": now()}],
        "offers": offers,
        "inputs": inputs,
        "max_loops_per_agent": MAX_LOOPS,
    }
    dump_json(run_dir / "state.json", state)
    print(f"Initialised {run_dir} with offers: {', '.join(offers)}")
    for oid, o in offers.items():
        print(f"  {oid}: {o['vendor']} | {o['page_count']} pages | sha256 {o['sha256'][:12]}")
    if "cost_book" not in inputs:
        print("WARNING: no cost book. Landed cost will list excluded scope as UNPRICED.")
    print(f"NEXT: {NEXT_ACTION['initialized']}")


def cmd_status(a: argparse.Namespace) -> None:
    run_dir = Path(a.run_dir).resolve()
    st = load_json(run_dir / "state.json")
    print(f"Project: {st['project']}")
    print(f"Phase:   {st['phase']}")
    for oid, o in st["offers"].items():
        loops = ", ".join(f"A{k}={v}" for k, v in o["loops"].items() if v)
        print(f"  {oid} ({o['vendor']}): gate={o.get('gate_verdict')} loops[{loops or 'none'}]")
    print(f"NEXT: {NEXT_ACTION[st['phase']]}")


def cmd_advance(a: argparse.Namespace) -> None:
    run_dir = Path(a.run_dir).resolve()
    st = load_json(run_dir / "state.json")
    cur = PHASES.index(st["phase"])
    target = PHASES.index(a.phase)
    if target != cur + 1:
        die(f"cannot move from {st['phase']} to {a.phase}; next allowed is {PHASES[min(cur + 1, len(PHASES) - 1)]}")
    if a.phase == "validation_complete":
        bad = [oid for oid, o in st["offers"].items() if o.get("gate_verdict") not in ("PASS", "PASS_WITH_CLARIFICATIONS")]
        if bad:
            die(f"gate has not passed for: {', '.join(bad)}. Run admin_gate.py (with --finalize if loop budget is spent).")
    st["phase"] = a.phase
    st["history"].append({"phase": a.phase, "at": now()})
    dump_json(run_dir / "state.json", st)
    print(f"Phase -> {a.phase}\nNEXT: {NEXT_ACTION[a.phase]}")


def cmd_loop(a: argparse.Namespace) -> None:
    run_dir = Path(a.run_dir).resolve()
    st = load_json(run_dir / "state.json")
    if a.offer not in st["offers"]:
        die(f"unknown offer {a.offer}")
    loops = st["offers"][a.offer]["loops"]
    key = str(a.agent)
    if loops.get(key, 0) >= MAX_LOOPS:
        print(f"BUDGET_SPENT: agent {a.agent} on {a.offer} already looped {MAX_LOOPS} times. "
              f"Run admin_gate.py --finalize to convert open items into vendor clarifications.")
        sys.exit(3)
    loops[key] = loops.get(key, 0) + 1
    dump_json(run_dir / "state.json", st)
    print(f"Loop recorded: agent {a.agent} on {a.offer} = {loops[key]}/{MAX_LOOPS}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--run-dir", required=True)
    i.add_argument("--project", required=True)
    i.add_argument("--offer", action="append", required=True)
    i.add_argument("--cost-book")
    i.add_argument("--requirements")
    i.add_argument("--force", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("--run-dir", required=True)
    adv = sub.add_parser("advance")
    adv.add_argument("--run-dir", required=True)
    adv.add_argument("--phase", required=True, choices=PHASES[1:])
    lp = sub.add_parser("loop")
    lp.add_argument("--run-dir", required=True)
    lp.add_argument("--offer", required=True)
    lp.add_argument("--agent", required=True, type=int, choices=[1, 2, 3, 4, 5])
    a = p.parse_args()
    {"init": cmd_init, "status": cmd_status, "advance": cmd_advance, "loop": cmd_loop}[a.cmd](a)


if __name__ == "__main__":
    main()
