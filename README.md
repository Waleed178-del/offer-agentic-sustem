# Offer Agentic System

A Claude Code skill that audits, normalizes and compares industrial capital equipment offers (extrusion lines, presses, furnaces, handling systems) with a 7-agent hub-and-spoke architecture.

## Use

Open this repository in Claude Code and ask:

```
/offer-audit Audit and compare offers/omav_sms.pdf (OMAV/SMS) and offers/danieli.pdf (Danieli Breda). Cost book: inputs/cost_book.json. Requirement: must accept existing 7" tooling from an 1800 MT press.
```

The main session becomes the Admin orchestrator. It dispatches six subagents (`.claude/agents/offer-*.md`), gates their output with deterministic scripts, loops failed work back at most twice, and writes `offer_audit_runs/<run>/report/Executive_Procurement_Report.md` plus one vendor-ready RFQ clarification file per offer.

## Architecture

### Topology (hub and spoke)

Workers never talk to each other. Every payload, rejection and loop routes through the Admin.

```mermaid
flowchart TB
    U([User: offer PDFs, cost book, requirements]) --> ADMIN
    ADMIN["ADMIN ORCHESTRATOR<br/>State manager and decision engine<br/>(main Claude session, SKILL.md)"]
    ADMIN <--> A1["Agent 1<br/>Ingestion and Taxonomy<br/>Document Map, vision on CAD and P&ID"]
    ADMIN <--> A2["Agent 2<br/>Press and Hydraulics"]
    ADMIN <--> A3["Agent 3<br/>Thermal and Utilities"]
    ADMIN <--> A4["Agent 4<br/>Downstream and Handling"]
    ADMIN <--> A5["Agent 5<br/>Scope, Exclusions, Risk<br/>(Red Team, full document)"]
    ADMIN <--> A6["Agent 6<br/>Cross-Offer Normalizer<br/>and Comparator"]
    ADMIN --> R([Executive Procurement Report<br/>+ RFQ dossier per vendor])

    classDef admin fill:#1f3a5f,color:#fff,stroke:#0d1b2a
    classDef worker fill:#e8eef5,color:#0d1b2a,stroke:#1f3a5f
    classDef red fill:#fbe3e3,color:#5a0000,stroke:#a00
    class ADMIN admin
    class A1,A2,A3,A4,A6 worker
    class A5 red
```

### Workflow (deterministic state machine)

Agents read and judge. Scripts verify and calculate. State is saved to `state.json` after every phase.

```mermaid
flowchart TD
    START([state.py init]) --> P1

    subgraph P1["Phase 1: Ingestion and Structural Mapping"]
        direction TB
        PS["prescan.py<br/>text layer, trap lexicon,<br/>spreadsheet error cells, blank cells,<br/>render drawing pages"] --> AG1["Agent 1 per offer (parallel)<br/>section tree, vision transcriptions"]
        AG1 --> VDM{"validate_payload.py<br/>--document-map"}
        VDM -- fail --> AG1
    end

    VDM -- pass --> P2

    subgraph P2["Phase 2: Parallel Domain Extraction"]
        direction TB
        RS["route_sections.py<br/>dispatch slices per worker"] --> PAR
        subgraph PAR["one parallel message, all offers"]
            direction LR
            W2[Agent 2] ~~~ W3[Agent 3] ~~~ W4[Agent 4] ~~~ W5[Agent 5]
        end
    end

    PAR --> P3

    subgraph P3["Phase 3: Validation and Conflict Loop"]
        direction TB
        VP["validate_payload.py<br/>R1 schema, R2 verbatim quote on cited page"] --> GATE["admin_gate.py<br/>R3 contradiction, R4 missing data,<br/>R5 scope blur, R6 coverage, R7 corruption"]
        GATE --> V{verdict}
        V -- "LOOP and budget left (max 2)" --> LO["loop_orders/agent_N.json<br/>state.py loop"]
        LO --> RW["Re-dispatch only the named workers"]
        RW --> VP
        V -- "budget spent" --> FIN["admin_gate.py --finalize<br/>open items become vendor clarifications"]
    end

    V -- "PASS / PASS_WITH_CLARIFICATIONS" --> P4
    FIN --> P4

    subgraph P4["Phase 4: Cross-Offer Normalization and Synthesis"]
        direction TB
        NO["normalize_offer.py<br/>verified findings to SI units"] --> AG6["Agent 6<br/>alignment.json: aliases, mandatory options,<br/>cost adders, branches, baselines"]
        AG6 --> BM["build_matrix.py<br/>parity, landed cost, branches, dossier<br/>(all arithmetic, UNPRICED counted)"]
        BM --> ADJ["Admin writes admin_adjudication.md"]
        ADJ --> RR["render_report.py"]
    end

    RR --> OUT([Executive_Procurement_Report.md<br/>RFQ_Clarifications_OFFER.md])
```

### Loop example: blank utility table (rule R4)

```mermaid
sequenceDiagram
    participant A3 as Agent 3
    participant AD as Admin
    participant G as admin_gate.py
    participant U as normalize_units.py
    A3->>AD: payload: utilities.natural_gas.max_flow = MISSING_DATA (p.16)
    AD->>G: run gate
    G-->>AD: LOOP, order for Agent 3: derive bottom up
    AD->>A3: loop_orders/agent_3.json
    A3->>U: sum "430 Nm3/h" "120 Nm3/h"
    U-->>A3: total 550.0 Nm3/h (JSON)
    A3->>AD: DERIVED_ESTIMATE 550 Nm3/h + tool_output + input ids
    AD->>G: rerun gate
    G-->>AD: PASS_WITH_CLARIFICATIONS (vendor must still populate p.16)
```

### Roster

| Agent | Role | Subagent | Spec |
|---|---|---|---|
| Admin | Orchestrator and decision engine | main session | `.claude/skills/offer-audit/SKILL.md` |
| 1 | Ingestion and taxonomy parser (vision for CAD and P&ID) | `offer-ingestion-parser` | `agents/agent-1-ingestion.md` |
| 2 | Press and hydraulics | `offer-press-hydraulics` | `agents/agent-2-press-hydraulics.md` |
| 3 | Thermal, combustion, utilities | `offer-thermal-utilities` | `agents/agent-3-thermal-utilities.md` |
| 4 | Downstream and handling | `offer-downstream-handling` | `agents/agent-4-downstream-handling.md` |
| 5 | Scope, exclusions, risk (red team) | `offer-risk-redteam` | `agents/agent-5-risk-redteam.md` |
| 6 | Cross-offer normalizer and comparator | `offer-normalizer-comparator` | `agents/agent-6-normalizer-comparator.md` |

Deterministic layer (`.claude/skills/offer-audit/scripts/`, Python standard library, poppler-utils):

| Script | Phase | Purpose |
|---|---|---|
| `state.py` | all | Phase state machine, loop budget, resumability |
| `prescan.py` | 1 | Text layer, trap lexicon scan, corrupted cells, blank cells, vision queue renders |
| `merge_document_map.py` | 1 | Merge sharded Agent 1 output on long documents |
| `route_sections.py` | 2 | Slice the Document Map into per-worker dispatch files |
| `validate_payload.py` | 1, 3 | Schema check and verbatim evidence verification against page text |
| `admin_gate.py` | 3 | Rules R1 to R7: schema, evidence, contradiction, missing data, scope blur, coverage, corruption |
| `normalize_units.py` | 3, 4 | SI conversion, sums and per-tonne figures for derivations |
| `normalize_offer.py` | 4 | Verified findings to SI records |
| `build_matrix.py` | 4 | Parity table, landed cost, branches, dossier. All arithmetic lives here |
| `render_report.py` | 4 | Executive report and RFQ dossiers |

## Requirements

* Claude Code (subagents, Read tool with PDF page support)
* Python 3.10 or newer, `poppler-utils` (`pdftotext`, `pdftoppm`, `pdfinfo`, `pdfimages`)
* Optional: `jsonschema` (built-in fallback validator otherwise), `reportlab` (tests only)

## Test

```bash
python3 -m unittest discover -s .claude/skills/offer-audit/tests -v
```

The test builds two synthetic offers seeded with the reference trap patterns (7 inch promise vs optional container, blank utility gas flow, pneumatic vs electric shuttle, `#VALORE!`, excluded cabling, buyer-supplied fencing, a fabricated quote) and runs the full deterministic pipeline including a rework loop.

## Cost book

Copy `.claude/skills/offer-audit/config/cost_book.example.json`, fill real figures with their source. Missing entries are reported as UNPRICED. The system never invents prices.
