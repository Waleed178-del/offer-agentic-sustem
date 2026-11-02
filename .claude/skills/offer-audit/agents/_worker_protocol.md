# Shared Worker Protocol (Agents 2 to 5)

Read this together with your own spec. It overrides any habit you have.

## Inputs

The Admin gives you `RUN_DIR`, `OFFER_ID`, `SKILL_DIR` and a dispatch file path (`RUN_DIR/OFFER_ID/dispatch/agent_N.json`). On a rework loop it also gives a loop order file (`RUN_DIR/OFFER_ID/gate/loop_orders/agent_N.json`).

The dispatch file lists your `sections` (with page ranges and PRIMARY or SECONDARY role), `required_section_ids`, `pages`, `drawings`, `corruption`, `blank_fields`, and the `output` path.

## Reading order

1. The dispatch file and `SKILL_DIR/references/data_contract.md`.
2. Buyer requirements file if `requirements` is not null.
3. For each assigned section, in order: `corpus/pages/NNN.txt` and, if present, `corpus/pages/NNN.vlm.md` for every page in the range. Read the whole section. Footnotes and table notes are where liabilities hide.
4. If a page's text is scrambled and no `.vlm.md` exists, Read the PDF page directly (`pages` parameter). Cite it as `TABLE` or `DRAWING` and note in `self_check.notes` that Agent 1 missed it.

## Writing findings

* One finding per atomic fact. "Main force 22.9 MN" and "side cylinders 2.4 MN" are two findings.
* `evidence_quote` is copied character for character from the page text or VLM transcription. Shortest span that proves the value. Use `...` to join two verbatim fragments from the same page. The validator checks it against the page. A paraphrase fails and gets your finding quarantined.
* `source_page` is the PDF page number (1-based), not the printed page label, unless they coincide.
* `item_key` uses the canonical keys in `SKILL_DIR/references/domain_taxonomy.md`. If none fits use `x.<subsystem>.<term>` and Agent 6 will align it.
* `value` is the number as printed, `unit` exactly as printed (`MN`, `US ton`, `Nm3/h`, `kW`, `"`). Do not convert units. The scripts do that.
* `status`: `INCLUDED_BASE` or `STATED` for base scope, `OPTIONAL`, `ALTERNATIVE`, `EXCLUDED_FROM_SUPPLY`, `BUYER_SUPPLY`, `PRELIMINARY` for approximate, indicative or to be confirmed values, `MISSING_DATA` for blank cells, `CORRUPTED_VALUE` for spreadsheet errors you cannot recover, `CONFLICTING_SPECS` for internal contradictions.
* `confidence`: 0.95 or above only for clean verbatim table or text values. 0.6 to 0.8 for values read from drawings or reconstructed tables.
* Contradictions: set `category: TECHNICAL_CONTRADICTION`, `status: CONFLICTING_SPECS`, and put one `supporting_evidence` entry per side (each a verbatim quote with its page). `evidence_quote` may then summarize.
* Derived values: never compute in your head. Run `python3 SKILL_DIR/scripts/normalize_units.py sum "120 Nm3/h" "430 Nm3/h"` (or `per-tonne`, `convert`) and paste the exact JSON stdout into `derivation.tool_output`, list `derivation.input_finding_ids`, set `evidence_type: DERIVED`, `status: DERIVED_ESTIMATE`.
* Prices: when the offer prints a price for an option or alternative, put it in `option_price` with ISO currency.
* Link base items and their alternatives with the same `alternative_group` string.
* Exclusions and buyer supply: set `cost_adder_key` from the cost book keys in `SKILL_DIR/config/cost_book.example.json` when one fits (`field_cabling`, `safety_fencing`, `safety_devices`, `foundations_civil`, `erection_labour`, `hydraulic_oil_first_fill`, `scrap_boxes`), else a new snake_case key.
* Corruption: every `corruption` id in your dispatch must appear in `acknowledged_corruptions`. Try to recover the value from the metric column, from another page or a drawing and cite that page. Otherwise emit `CORRUPTED_VALUE`.
* Blank fields in your dispatch: emit a `MISSING_DATA` finding quoting the field label.

## Payload

Write `output` from the dispatch file. Conform to `SKILL_DIR/schemas/worker_payload.schema.json`. `finding_id` is `A<N>-001`, `A<N>-002` and so on. `sections_covered` lists every section id you actually read, including SECONDARY ones. `pages_read` lists every page.

Self-check before returning, then run:

```bash
python3 SKILL_DIR/scripts/validate_payload.py --run-dir RUN_DIR --offer OFFER_ID
```

Fix every `FAILED` finding that belongs to you (ids `A<N>-`). Ignore failures from other agents. Then set the three `self_check` booleans honestly. A false flag is allowed and better than a lie. It sends you back for rework.

## On a rework loop

Read the loop order file. Apply every order. Keep all findings that were not challenged. Rewrite the full payload, set `loop_iteration`. Do not delete a finding to make an order go away unless the order says the evidence does not exist.

## Return to Admin

At most 8 lines: finding counts by category, top 3 issues by financial impact, anything you could not read. No JSON in the reply. The file is the deliverable.

## Never

* Talk to or rely on other workers' output, except reading other agents' payload files to cite `input_finding_ids` in a derivation.
* Write outside your payload file, except running the validator.
* Fill a blank with a typical industry value. Missing is a finding, not a gap to paper over.
