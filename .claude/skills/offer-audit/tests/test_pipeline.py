#!/usr/bin/env python3
"""End-to-end test of the deterministic layer with two synthetic offers.

Offer A is seeded with the trap patterns of the reference OMAV/SMS offer:
promise of 7 inch capability with the 7 inch container listed as optional,
blank utility gas flow with values scattered in sub-equipment, a pneumatic
vs electric shuttle contradiction, #VALORE! corruption, excluded cabling
and buyer-supplied safety fences. Offer B is a clean competitor quoted in
US tons. Worker payloads are simulated; the scripts under test are real.

Run:  python3 -m unittest discover -s .claude/skills/offer-audit/tests -v
Requires reportlab (fixture generation) and poppler-utils.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import normalize_units as nu  # noqa: E402


def run(script: str, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True)
    if ok and p.returncode != 0:
        raise AssertionError(f"{script} {' '.join(args)} failed ({p.returncode}):\n{p.stdout}\n{p.stderr}")
    return p


def make_pdf(path: Path, pages: list[list[str]]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            c.drawString(50, y, line)
            y -= 18
        c.showPage()
    c.save()


OFFER_A = [
    ["OFFER XX-26 EXTRUSION LINE 25 MN", "HIGHLIGHTS", "The line is designed to process 8\" and 7\" billets with the existing tools.",
     "Front loading short stroke press with high productivity and low energy consumption."],
    ["1 PLANT UTILITY DATA", "Installed electrical power            2500 kW", "Natural gas max flow rate            Nm3/h",
     "Compressed air pressure              6 bar", "Imperial column   #VALORE!", "Reference production rate 2000 kg/h",
     "The utility consumption values are given for a reference production of 2000 kg/h."],
    ["2 EXTRUSION PRESS", "Main cylinder force 22.9 MN", "Side cylinders force 2.4 MN", "Dead cycle time 12.7 s",
     "Billet container diameter 8\" included in base supply.", "Main pumps: 3 x Rexroth A4VSO, 200 kW each."],
    ["2.7 OPTIONS", "2.7.3 Billet container 7\" - OPTIONAL - price 185,000 EUR", "2.7.4 Extrusion tools for 7\" - OPTIONAL",
     "1.5 HORIZONTAL SHUTTLE", "DRIVE: Pneumatic"],
    ["The shuttle carried out the horizontal transfer by means of electric motor.", "3 LOG FURNACE HP6",
     "Capacity 4000 kg/h", "Gas flow to burners 430 Nm3/h", "4 AGEING OVEN", "Burner gas flow 120 Nm3/h"],
    ["EXCLUSIONS AND BUYER SUPPLY", "The supply does not include electrical cables and needed electrical material (e.g. raceway)",
     "of connection from electrical panel to equipment and control desk.", "Customer will supply: Complete safety fences and doors.",
     "TOTAL PRICE EXW 4,200,000 EUR"],
]
OFFER_B = [
    ["COMPETITOR OFFER 2800 US TON PRESS", "Press total force 2800 US ton", "Dead cycle time 14 s"],
    ["UTILITIES", "Natural gas max flow rate 600 Nm3/h", "Reference production rate 3000 kg/h", "Field cabling included in supply."],
    ["COMMERCIAL", "TOTAL PRICE EXW 4,500,000 EUR"],
]


def finding(fid, cat, item, key, status, quote, page, value=None, unit=None, attribute=None, impact="LOW", etype="TEXT", **extra):
    f = {"finding_id": fid, "category": cat, "item": item, "item_key": key, "status": status, "evidence_quote": quote,
         "source_page": page, "evidence_type": etype, "confidence": 0.95, "financial_impact": impact,
         "action_required": "Confirm with vendor."}
    if value is not None:
        f["value"] = value
    if unit is not None:
        f["unit"] = unit
    if attribute is not None:
        f["attribute"] = attribute
    f.update(extra)
    return f


def payload(offer, agent_id, findings, sections, pages, acked=None):
    return {"offer_id": offer, "agent_id": agent_id, "subsystem": "test", "sections_covered": sections, "pages_read": pages,
            "extracted_findings": findings, "acknowledged_corruptions": acked or [], "open_questions": [],
            "self_check": {"all_quotes_verbatim": True, "all_assigned_sections_read": True, "no_values_inferred_without_derivation": True}}


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


class UnitTests(unittest.TestCase):
    def test_force(self):
        self.assertAlmostEqual(nu.to_si(2800, "US ton")["value"], 24.909, places=2)
        self.assertAlmostEqual(nu.to_si(60, "MTon")["value"], 0.5884, places=3)
        with self.assertRaises(nu.UnitError):
            nu.to_si(10, "ton")

    def test_sum_and_per_tonne(self):
        s = nu.sum_quantities(["120 Nm3/h", "430 Nm3/h"])
        self.assertEqual(s["total"], 550.0)
        self.assertEqual(nu.per_tonne("430 Nm3/h", "4000 kg/h")["value"], 107.5)
        with self.assertRaises(nu.UnitError):
            nu.sum_quantities(["120 Nm3/h", "5 kW"])

    def test_inches(self):
        self.assertAlmostEqual(nu.to_si(7, '"')["value"], 177.8)


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("reportlab not installed")
        if not shutil.which("pdftotext"):
            raise unittest.SkipTest("poppler-utils not installed")
        cls.tmp = Path(tempfile.mkdtemp(prefix="offer_audit_test_"))
        make_pdf(cls.tmp / "a.pdf", OFFER_A)
        make_pdf(cls.tmp / "b.pdf", OFFER_B)
        book = json.loads((SKILL / "config" / "cost_book.example.json").read_text())
        book["items"]["field_cabling"].update(low=150000, high=220000, source="test")
        book["items"]["safety_fencing"].update(low_per_unit=180, high_per_unit=260, default_quantity=400, source="test")
        write(cls.tmp / "cost_book.json", book)
        cls.run_dir = cls.tmp / "run"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_full_pipeline(self):
        rd = str(self.run_dir)
        run("state.py", "init", "--run-dir", rd, "--project", "Test Line",
            "--offer", f"OFFER_A={self.tmp / 'a.pdf'}:OMAV/SMS", "--offer", f"OFFER_B={self.tmp / 'b.pdf'}:Competitor B",
            "--cost-book", str(self.tmp / "cost_book.json"))
        for o in ("OFFER_A", "OFFER_B"):
            out = run("prescan.py", "--run-dir", rd, "--offer", o, "--no-render").stdout
            self.assertIn("pages", out)
        pre = json.loads((self.run_dir / "OFFER_A" / "prescan.json").read_text())
        self.assertEqual(len(pre["corruption"]), 1)
        self.assertGreaterEqual(pre["lexicon_hit_counts"]["exclusion"], 1)
        self.assertGreaterEqual(pre["lexicon_hit_counts"]["buyer_supply"], 1)
        self.assertTrue(any(b["page"] == 2 for b in pre["blank_cell_candidates"]))

        # ---- Agent 1 (simulated)
        dm_a = {"offer_id": "OFFER_A", "agent_id": "AGENT_1_INGESTION", "vendor": "OMAV/SMS", "page_count": 6, "ocr_required": False,
                "sections": [
                    {"section_id": "FRONT", "title": "Highlights", "page_start": 1, "page_end": 1, "domain": "GENERAL"},
                    {"section_id": "1", "title": "Plant Utility Data", "page_start": 2, "page_end": 2, "domain": "UTILITIES"},
                    {"section_id": "2", "title": "Extrusion Press", "page_start": 3, "page_end": 3, "domain": "PRESS"},
                    {"section_id": "2.7", "title": "Options", "page_start": 4, "page_end": 4, "domain": "OPTIONS", "base_or_option": "OPTION"},
                    {"section_id": "3", "title": "Log Furnace and Ageing Oven", "page_start": 5, "page_end": 5, "domain": "FURNACE"},
                    {"section_id": "9", "title": "Exclusions", "page_start": 6, "page_end": 6, "domain": "SCOPE_SPLIT"}],
                "drawings": [], "data_corruption": [{"corruption_id": "C-001", "page": 2, "token": "#VALORE!", "context": "Imperial column #VALORE!", "owning_domain": "UTILITIES"}],
                "blank_fields": [{"page": 2, "field": "Natural gas max flow rate", "owning_domain": "UTILITIES"}], "boilerplate_pages": []}
        dm_b = {"offer_id": "OFFER_B", "agent_id": "AGENT_1_INGESTION", "vendor": "Competitor B", "page_count": 3, "ocr_required": False,
                "sections": [
                    {"section_id": "1", "title": "Press", "page_start": 1, "page_end": 1, "domain": "PRESS"},
                    {"section_id": "2", "title": "Utilities", "page_start": 2, "page_end": 2, "domain": "UTILITIES"},
                    {"section_id": "3", "title": "Commercial", "page_start": 3, "page_end": 3, "domain": "COMMERCIAL"}],
                "drawings": [], "data_corruption": [], "blank_fields": [], "boilerplate_pages": []}
        write(self.run_dir / "OFFER_A" / "document_map.json", dm_a)
        write(self.run_dir / "OFFER_B" / "document_map.json", dm_b)
        for o in ("OFFER_A", "OFFER_B"):
            run("validate_payload.py", "--run-dir", rd, "--offer", o, "--document-map")
        run("state.py", "advance", "--run-dir", rd, "--phase", "ingestion_complete")
        for o in ("OFFER_A", "OFFER_B"):
            run("route_sections.py", "--run-dir", rd, "--offer", o)
        d3 = json.loads((self.run_dir / "OFFER_A" / "dispatch" / "agent_3.json").read_text())
        self.assertIn("1", d3["required_section_ids"])
        self.assertEqual(d3["corruption"][0]["corruption_id"], "C-001")

        # ---- Agents 2-5 (simulated) Offer A
        pa = self.run_dir / "OFFER_A" / "payloads"
        write(pa / "agent_2.json", payload("OFFER_A", "AGENT_2_PRESS_HYDRAULICS", [
            finding("A2-001", "TECHNICAL_SPEC", "Main cylinder force", "press.main_force", "INCLUDED_BASE", "Main cylinder force 22.9 MN", 3, 22.9, "MN"),
            finding("A2-002", "TECHNICAL_SPEC", "Side cylinders force", "press.side_force", "INCLUDED_BASE", "Side cylinders force 2.4 MN", 3, 2.4, "MN"),
            finding("A2-003", "TECHNICAL_SPEC", "Dead cycle time", "press.dead_cycle_time", "STATED", "Dead cycle time 12.7 s", 3, 12.7, "s"),
            finding("A2-004", "TECHNICAL_SPEC", "Container 8 inch", "press.container.diameter", "INCLUDED_BASE", "Billet container diameter 8\" included in base supply.", 3, 8, '"', attribute="8in"),
            finding("A2-005", "OPTIONAL_ITEM", "Container 7 inch", "press.container.diameter", "OPTIONAL", "2.7.3 Billet container 7\" - OPTIONAL - price 185,000 EUR", 4, 7, '"', attribute="7in", impact="HIGH",
                    option_price={"amount": 185000, "currency": "EUR"}),
            finding("A2-006", "TECHNICAL_CONTRADICTION", "Horizontal shuttle drive", "feeding.horizontal_shuttle.drive", "CONFLICTING_SPECS", "Table pneumatic, text electric", 4,
                    supporting_evidence=[{"quote": "DRIVE: Pneumatic", "page": 4, "evidence_type": "TABLE"},
                                         {"quote": "The shuttle carried out the horizontal transfer by means of electric motor", "page": 5}]),
        ], ["2"], [3, 4, 5]))
        a3 = [
            finding("A3-001", "UTILITY_CONSUMPTION", "Natural gas max flow (plant)", "utilities.natural_gas.max_flow", "MISSING_DATA", "Natural gas max flow rate Nm3/h", 2, impact="MEDIUM"),
            finding("A3-002", "UTILITY_CONSUMPTION", "Furnace gas flow", "furnace.gas_flow_max", "STATED", "Gas flow to burners 430 Nm3/h", 5, 430, "Nm3/h"),
            finding("A3-003", "UTILITY_CONSUMPTION", "Ageing oven gas flow", "ageing_oven.gas_flow", "STATED", "Burner gas flow 120 Nm3/h", 5, 120, "Nm3/h"),
            finding("A3-004", "TECHNICAL_SPEC", "Furnace capacity", "furnace.capacity", "STATED", "Capacity 4000 kg/h", 5, 4000, "kg/h"),
        ]
        write(pa / "agent_3.json", payload("OFFER_A", "AGENT_3_THERMAL_UTILITIES", a3, ["1", "3"], [2, 5], acked=["C-001"]))
        write(pa / "agent_4.json", payload("OFFER_A", "AGENT_4_DOWNSTREAM_HANDLING", [], [], []))
        write(pa / "agent_5.json", payload("OFFER_A", "AGENT_5_RISK_AND_SCOPE", [
            finding("A5-001", "SCOPE_PROMISE", "7 inch billet capability", "press.container.diameter", "STATED", "The line is designed to process 8\" and 7\" billets with the existing tools.", 1, attribute="7in", impact="HIGH"),
            finding("A5-002", "HIDDEN_CAPEX_EXCLUSION", "Field cabling", "scope.field_cabling", "EXCLUDED_FROM_SUPPLY",
                    "The supply does not include electrical cables and needed electrical material (e.g. raceway)", 6, impact="HIGH", cost_adder_key="field_cabling"),
            finding("A5-003", "BUYER_SUPPLY", "Safety fences", "scope.safety_fencing", "BUYER_SUPPLY", "Customer will supply: Complete safety fences and doors.", 6, impact="MEDIUM", cost_adder_key="safety_fencing"),
            finding("A5-004", "COMMERCIAL_TERM", "Headline price", "commercial.headline_price", "STATED", "TOTAL PRICE EXW 4,200,000 EUR", 6, 4200000, "EUR"),
            finding("A5-005", "HIDDEN_CAPEX_EXCLUSION", "Fabricated exclusion", "scope.foundations_civil", "EXCLUDED_FROM_SUPPLY", "Foundations are excluded from the supply of the vendor", 6, impact="HIGH"),
        ], ["FRONT", "2.7", "9"], [1, 2, 3, 4, 5, 6]))

        # Offer B
        pb = self.run_dir / "OFFER_B" / "payloads"
        write(pb / "agent_2.json", payload("OFFER_B", "AGENT_2_PRESS_HYDRAULICS", [
            finding("A2-001", "TECHNICAL_SPEC", "Press total force", "press.total_force", "STATED", "Press total force 2800 US ton", 1, 2800, "US ton"),
            finding("A2-002", "TECHNICAL_SPEC", "Dead cycle time", "press.dead_cycle_time", "STATED", "Dead cycle time 14 s", 1, 14, "s"),
        ], ["1"], [1]))
        write(pb / "agent_3.json", payload("OFFER_B", "AGENT_3_THERMAL_UTILITIES", [
            finding("A3-001", "UTILITY_CONSUMPTION", "Natural gas max flow (plant)", "utilities.natural_gas.max_flow", "STATED", "Natural gas max flow rate 600 Nm3/h", 2, 600, "Nm3/h"),
        ], ["2"], [2]))
        write(pb / "agent_4.json", payload("OFFER_B", "AGENT_4_DOWNSTREAM_HANDLING", [], [], []))
        write(pb / "agent_5.json", payload("OFFER_B", "AGENT_5_RISK_AND_SCOPE", [
            finding("A5-001", "COMMERCIAL_TERM", "Headline price", "commercial.headline_price", "STATED", "TOTAL PRICE EXW 4,500,000 EUR", 3, 4500000, "EUR"),
        ], ["3"], [1, 2, 3]))
        run("state.py", "advance", "--run-dir", rd, "--phase", "extraction_complete")

        # ---- Phase 3 gate, Offer A first pass must LOOP
        p = run("validate_payload.py", "--run-dir", rd, "--offer", "OFFER_A", ok=False)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("FAILED A5-005", p.stdout)  # fabricated quote caught
        run("admin_gate.py", "--run-dir", rd, "--offer", "OFFER_A")
        gate = json.loads((self.run_dir / "OFFER_A" / "gate" / "gate_report.json").read_text())
        self.assertEqual(gate["verdict"], "LOOP")
        self.assertEqual(len(gate["red_flags"]), 1)  # R5: 7in promise vs optional, 8in not matched
        self.assertEqual(gate["red_flags"][0]["contradicting_scope"]["finding_id"], "A2-005")
        self.assertTrue((self.run_dir / "OFFER_A" / "gate" / "loop_orders" / "agent_3.json").exists())  # R4
        self.assertTrue((self.run_dir / "OFFER_A" / "gate" / "loop_orders" / "agent_5.json").exists())  # R2
        cats = {q["category"] for q in gate["clarifications"]}
        self.assertIn("TECHNICAL_CONTRADICTION", cats)
        self.assertIn("SCOPE_BLUR", cats)

        # ---- Loop: Agent 3 derives bottom-up, Agent 5 drops fabricated finding
        run("state.py", "loop", "--run-dir", rd, "--offer", "OFFER_A", "--agent", "3")
        run("state.py", "loop", "--run-dir", rd, "--offer", "OFFER_A", "--agent", "5")
        tool = run("normalize_units.py", "sum", "430 Nm3/h", "120 Nm3/h").stdout.strip()
        self.assertEqual(json.loads(tool)["total"], 550.0)
        a3.append(finding("A3-005", "UTILITY_CONSUMPTION", "Natural gas max flow (bottom-up)", "utilities.natural_gas.max_flow", "DERIVED_ESTIMATE",
                          "Sum of furnace and ageing oven burner flows", 2, 550, "Nm3/h", impact="MEDIUM", etype="DERIVED",
                          derivation={"method": "sum furnace + ageing oven, lower bound", "input_finding_ids": ["A3-002", "A3-003"], "tool_output": tool}))
        a3.append(finding("A3-006", "UTILITY_CONSUMPTION", "Reference production rate", "utilities.reference_rate", "STATED", "Reference production rate 2000 kg/h", 2, 2000, "kg/h"))
        p3 = payload("OFFER_A", "AGENT_3_THERMAL_UTILITIES", a3, ["1", "3"], [2, 5], acked=["C-001"])
        p3["loop_iteration"] = 1
        write(pa / "agent_3.json", p3)
        p5 = json.loads((pa / "agent_5.json").read_text())
        p5["extracted_findings"] = [f for f in p5["extracted_findings"] if f["finding_id"] != "A5-005"]
        p5["loop_iteration"] = 1
        write(pa / "agent_5.json", p5)

        run("validate_payload.py", "--run-dir", rd, "--offer", "OFFER_A")
        run("admin_gate.py", "--run-dir", rd, "--offer", "OFFER_A")
        gate = json.loads((self.run_dir / "OFFER_A" / "gate" / "gate_report.json").read_text())
        self.assertEqual(gate["verdict"], "PASS_WITH_CLARIFICATIONS", json.dumps(gate["loop_orders"]))
        self.assertTrue(gate["clarifications"][0]["priority"] == "P1")

        run("validate_payload.py", "--run-dir", rd, "--offer", "OFFER_B")
        run("admin_gate.py", "--run-dir", rd, "--offer", "OFFER_B")
        run("state.py", "advance", "--run-dir", rd, "--phase", "validation_complete")

        # ---- Phase 4
        for o in ("OFFER_A", "OFFER_B"):
            run("normalize_offer.py", "--run-dir", rd, "--offer", o)
        alignment = {
            "agent_id": "AGENT_6_NORMALIZER", "offers": ["OFFER_A", "OFFER_B"], "report_currency": "EUR",
            "key_aliases": [],
            "headline_prices": [{"offer_id": "OFFER_A", "amount": 4200000, "currency": "EUR", "finding_id": "A5-004", "incoterm": "EXW"},
                                {"offer_id": "OFFER_B", "amount": 4500000, "currency": "EUR", "finding_id": "A5-001", "incoterm": "EXW"}],
            "mandatory_options": [{"offer_id": "OFFER_A", "finding_id": "A2-005", "reason": "Existing 7 inch tooling must be used"}],
            "cost_adders": [{"offer_id": "OFFER_A", "finding_id": "A5-002", "cost_adder_key": "field_cabling"},
                            {"offer_id": "OFFER_A", "finding_id": "A5-003", "cost_adder_key": "safety_fencing"}],
            "branches": [],
            "baselines": [{"offer_id": "OFFER_A", "item_key": "utilities.natural_gas.max_flow", "reference_rate_kg_h": 2000, "max_rate_kg_h": 4000},
                          {"offer_id": "OFFER_B", "item_key": "utilities.natural_gas.max_flow", "reference_rate_kg_h": 3000, "max_rate_kg_h": None}],
            "notes": ["Offer B force quoted in short tons-force."],
        }
        write(self.run_dir / "comparison" / "alignment.json", alignment)
        run("build_matrix.py", "--run-dir", rd)
        m = json.loads((self.run_dir / "comparison" / "matrix.json").read_text())
        lc = m["landed_cost"]["OFFER_A"]
        self.assertEqual(lc["total_low"], 4200000 + 185000 + 150000 + 72000)
        self.assertEqual(lc["total_high"], 4200000 + 185000 + 220000 + 104000)
        self.assertEqual(lc["unpriced_count"], 0)
        rows = {(r["item_key"], r["attribute"]): r for r in m["parity"]}
        self.assertAlmostEqual(rows[("press.total_force", "value")]["offers"]["OFFER_B"]["value"], 24.909, places=2)
        gas = rows[("utilities.natural_gas.max_flow", "value")]
        self.assertIn("BASELINE_MISMATCH", gas["row_flags"])
        self.assertEqual(rows[("utilities.natural_gas.max_flow", "value@per_tonne")]["offers"]["OFFER_A"]["value"], 275.0)
        self.assertEqual(rows[("utilities.natural_gas.max_flow", "value@per_tonne")]["offers"]["OFFER_B"]["value"], 200.0)
        run("state.py", "advance", "--run-dir", rd, "--phase", "normalization_complete")

        (self.run_dir / "comparison" / "admin_adjudication.md").write_text("### Verdict\n\nTest adjudication.\n")
        run("render_report.py", "--run-dir", rd)
        rep = (self.run_dir / "report" / "Executive_Procurement_Report.md").read_text()
        for marker in ("View 1", "View 2", "View 3", "View 4", "Admin Adjudication", "SCOPE_BLUR", "4,607,000 EUR"):
            self.assertIn(marker, rep)
        self.assertTrue((self.run_dir / "report" / "RFQ_Clarifications_OFFER_A.md").exists())
        run("state.py", "advance", "--run-dir", rd, "--phase", "complete")

    def test_phase_skip_refused(self):
        rd = self.tmp / "skip"
        run("state.py", "init", "--run-dir", str(rd), "--project", "x", "--offer", f"OFFER_A={self.tmp / 'a.pdf'}:A")
        p = run("state.py", "advance", "--run-dir", str(rd), "--phase", "validation_complete", ok=False)
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
