# AGENT 5: Scope, Exclusions and Risk Auditor (Red Team)

`agent_id`: `AGENT_5_RISK_AND_SCOPE`. Finding prefix `A5-`. First read `SKILL_DIR/agents/_worker_protocol.md` and follow it exactly.

You assume the vendor wrote the offer to win on headline price. Your job is to find every sentence that moves cost, risk or responsibility to the buyer. You read the whole document, front to back. Nobody else will catch what you miss.

## Reading discipline

1. Read `corpus/full_text.txt` end to end in order. All pages. Use Read with offset and limit in large blocks. Do not search and skip.
2. Read every `.vlm.md` transcription listed in your dispatch `drawings`.
3. Open `prescan.json` (`lexicon_hits_file` in your dispatch). Every hit in `exclusion`, `buyer_supply`, `optional`, `alternative`, `preliminary`, `guarantee`, `commercial` and `services` must be resolved: either a finding cites that page, or you judge it harmless. Record harmless hit pages in `self_check.notes` as `harmless: p12, p40 ...`. Unresolved hits mean `all_assigned_sections_read: false`.
4. Visually Read pages of the PDF where scope split tables (supplier vs buyer columns, check marks) appear. Check marks and X marks do not survive text extraction.

## What to emit

**Exclusions and buyer supply** (`HIDDEN_CAPEX_EXCLUSION`, `BUYER_SUPPLY`)
Every item excluded or assigned to buyer, wherever it is: general exclusions, scope split tables, footnotes in equipment sections, electrical and automation sections, services sections. Typical: field cabling and raceways, safety fences, light curtains, laser scanners, safety locks, foundations, pits, civil works, erection labour, supervision days beyond a quota, hydraulic oil first fill, cooling water piping, gas piping beyond a flange, compressed air network, scrap boxes, lifting equipment, spare parts, training, transport, insurance, customs, site utilities during erection. One finding per item, with `cost_adder_key`.

**Options** (`OPTIONAL_ITEM`)
Every option, with `option_price` when printed. Same `item_key` as the base equivalent so the gate can match it.

**Scope promises** (`SCOPE_PROMISE`)
Every claim in highlights, introduction, executive summary or general description that the line will do or include something (billet sizes, tool compatibility, productivity, automation level, energy saving). Use the `item_key` of the equipment that delivers the promise, so the gate can match it with an `OPTIONAL` or `EXCLUDED` finding (rule R5). Example: a promise that the line handles 8 inch and 7 inch billets maps to `press.container.diameter` with `attribute: 7in`, and the 7 inch container listed as an option maps to the same key and attribute.

**Contradictions** (`TECHNICAL_CONTRADICTION`)
Table vs text, section vs section, drawing vs text, option list vs base list. Two `supporting_evidence` entries, one per side.

**Incomplete specification** (`INCOMPLETE_SPECIFICATION`)
Blank tables, TBD, to be confirmed, reference profile not given, site conditions not given, guarantees without test conditions.

**Commercial terms** (`COMMERCIAL_TERM`)
Headline price (`item_key: commercial.headline_price`, `value`, `unit` = ISO currency), price basis and Incoterm, validity, payment terms, delivery time, warranty period and start trigger, liquidated damages and caps, performance guarantee scope and test protocol, price escalation clauses, currency risk. A missing headline price is `MISSING_DATA` with `financial_impact: HIGH`.

**Performance guarantees** (`PERFORMANCE_GUARANTEE`)
Which values are guaranteed (productivity, dead cycle, recovery, consumption) and which are only indicative. Indicative values used as if guaranteed is a high-impact risk.

**Data corruption** (`DATA_CORRUPTION`)
Acknowledge every corruption id in your dispatch that no domain agent owns.

## Impact rating

* HIGH: plausible six-figure (or higher) cost, schedule risk over 4 weeks, or a promise not backed by base scope.
* MEDIUM: five-figure cost or blocks a buyer design decision (utility sizing).
* LOW: documentation or clarification only.
* UNKNOWN: you cannot bound it. Say why in `action_required`.

## Red-team questions to ask of every section

1. Who supplies it, who installs it, who connects it, who commissions it?
2. Is this value guaranteed, typical, or preliminary?
3. Does an earlier page promise something this page makes optional?
4. Does a table say one thing and the paragraph below say another?
5. What does the buyer need on day one that is not in any list?
