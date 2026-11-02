# Data Contract

Machine-enforced by `schemas/*.json`, `validate_payload.py` and `admin_gate.py`. This page explains intent.

## Run directory layout

```
offer_audit_runs/<run_id>/
  state.json                         phase, offers, loop counters, inputs
  inputs/                            cost book, requirements (copied)
  <OFFER_ID>/
    prescan.json                     deterministic lexicon and layout scan
    corpus/pages/NNN.txt             text layer per page
    corpus/pages/NNN.vlm.md          Agent 1 vision transcriptions
    corpus/images/page-NNN.png       renders for vision
    corpus/full_text.txt
    document_map.json                Agent 1
    dispatch/agent_{2..5}.json       route_sections.py
    payloads/agent_{2..5}.json       workers
    gate/validation.json             validate_payload.py
    gate/gate_report.json            admin_gate.py
    gate/risk_register.json          admin_gate.py
    gate/loop_orders/agent_N.json    admin_gate.py
    normalized/offer_normalized.json normalize_offer.py
  comparison/alignment.json          Agent 6
  comparison/matrix.json             build_matrix.py
  comparison/*.csv
  comparison/admin_adjudication.md   Admin
  report/Executive_Procurement_Report.md
  report/RFQ_Clarifications_<OFFER>.md
```

## Worker finding (example)

```json
{
  "finding_id": "A5-007",
  "category": "HIDDEN_CAPEX_EXCLUSION",
  "item": "Field Electrical Cabling & Raceways",
  "item_key": "scope.field_cabling",
  "status": "EXCLUDED_FROM_SUPPLY",
  "evidence_quote": "The OMAV supply does not include electrical cables and needed electrical material (e.g. raceway) of connection from electrical panel to equipment and control desk.",
  "source_page": 152,
  "evidence_type": "TEXT",
  "cost_adder_key": "field_cabling",
  "confidence": 0.97,
  "financial_impact": "HIGH",
  "action_required": "Request turnkey cabling quote or estimate local electrical contractor cost."
}
```

Contradiction:

```json
{
  "finding_id": "A2-031",
  "category": "TECHNICAL_CONTRADICTION",
  "item": "Horizontal Shuttle Drive Mechanism (Item 1.5)",
  "item_key": "feeding.horizontal_shuttle.drive",
  "status": "CONFLICTING_SPECS",
  "evidence_quote": "Table lists pneumatic drive, narrative lists electric motor.",
  "source_page": 38,
  "supporting_evidence": [
    {"quote": "DRIVE: Pneumatic", "page": 38, "evidence_type": "TABLE"},
    {"quote": "The shuttle carried out the horizontal transfer by means of electric motor", "page": 39, "evidence_type": "TEXT"}
  ],
  "evidence_type": "TABLE",
  "confidence": 0.9,
  "financial_impact": "LOW",
  "action_required": "Confirm electric vs pneumatic actuation and the related utility demand."
}
```

Derived bottom-up estimate:

```json
{
  "finding_id": "A3-044",
  "category": "UTILITY_CONSUMPTION",
  "item": "Natural gas max flow, plant total (bottom-up)",
  "item_key": "utilities.natural_gas.max_flow",
  "attribute": "value",
  "value": 550,
  "unit": "Nm3/h",
  "status": "DERIVED_ESTIMATE",
  "evidence_quote": "Sum of furnace gas train and ageing oven burner flows",
  "source_page": 16,
  "evidence_type": "DERIVED",
  "derivation": {
    "method": "sum of furnace (A3-012, p31 schematic) + ageing oven (A3-030, p134). Die ovens electric. Lower bound.",
    "input_finding_ids": ["A3-012", "A3-030"],
    "tool_output": "{\"operation\": \"sum\", \"parts\": [...], \"total\": 550.0, \"unit\": \"Nm3/h\"}"
  },
  "confidence": 0.7,
  "financial_impact": "MEDIUM",
  "action_required": "Vendor must populate p16. Use 550 Nm3/h as a lower bound for gas manifold sizing."
}
```

## Evidence verification outcomes

| Verdict | Meaning | Reaches comparison |
|---|---|---|
| VERIFIED_EXACT | normalized quote is a substring of the page | yes |
| VERIFIED_FUZZY | at least 85 percent of quote tokens on page (tables) | yes |
| VLM_ONLY | found only in Agent 1 vision transcription | yes, flagged |
| DERIVED_OK | derivation inputs exist and tool output attached | yes, flagged |
| FAILED | not found, wrong page, or missing proof | no, quarantined and looped |

## Status semantics for landed cost

* `INCLUDED_BASE`, `STATED`: in headline price.
* `OPTIONAL`: not in headline. Added only if Agent 6 lists it in `mandatory_options`.
* `ALTERNATIVE`: a branch. Priced in View 3, not added to landed cost.
* `EXCLUDED_FROM_SUPPLY`, `BUYER_SUPPLY`: added via `cost_adders` and the cost book. UNPRICED if no entry.
