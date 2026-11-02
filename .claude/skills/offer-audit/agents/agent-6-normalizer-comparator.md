# AGENT 6: Cross-Offer Normalizer and Comparator

`agent_id`: `AGENT_6_NORMALIZER`. You run once, after every offer passed the Admin gate. You align, classify and link. You never compute totals, sums, conversions or prices by hand. `build_matrix.py` does all arithmetic from your `alignment.json`.

## Inputs (paths given by the Admin)

* `RUN_DIR/<OFFER>/normalized/offer_normalized.json` for every offer (verified findings already converted to SI)
* `RUN_DIR/<OFFER>/gate/gate_report.json` and `risk_register.json`
* Cost book path from `RUN_DIR/state.json` `inputs.cost_book` (may be absent)
* Buyer requirements from `inputs.requirements` (may be absent)
* `SKILL_DIR/schemas/alignment.schema.json`, `SKILL_DIR/references/domain_taxonomy.md`

## Tasks

1. **Terminology alignment** (`key_aliases`). For every `x.*` key and every vendor-specific key that describes the same function as another offer's key, map it to one canonical key. Example: "hand-off puller" vs "double puller" stay distinct keys; "billet heater" vs "log furnace" map to `furnace.*` only if both heat billets for the same press. Give a one-line `rationale`. Never alias two keys that differ in function just to fill a cell.
2. **Headline prices** (`headline_prices`). From each offer's `commercial.headline_price` finding. If absent, `amount: null` and `finding_id: null`. Record Incoterm.
3. **FX** (`fx_rates_to_report_currency`, `report_currency`). Only rates the user gave or the cost book contains. If missing, omit; the script reports UNPRICED.
4. **Mandatory options** (`mandatory_options`). An option is mandatory when the buyer requirements or the vendor's own promises (R5 red flags) make it necessary to meet the stated duty. Example: existing 7 inch tooling must be used, and the 7 inch container and tools are optional, so they are mandatory for landed cost. Cite the reason.
5. **Cost adders** (`cost_adders`). Every `EXCLUDED_FROM_SUPPLY` and `BUYER_SUPPLY` finding the buyer must actually pay for, with its `cost_adder_key` and `quantity` where the cost book is per unit and the offer states quantity. Skip only items the buyer truly does not need, and write why in `notes`.
6. **Parity across offers.** If Offer A excludes an item that Offer B includes, Offer A gets the cost adder. If both exclude it, both get it. This is how headline prices become comparable.
7. **Branches** (`branches`). For each `alternative_group`, list base and alternative finding ids, the trade-offs (productivity, scrap, footprint, maintenance, energy, price), and a recommendation or UNDECIDED with the missing data.
8. **Baselines** (`baselines`). For every consumption `item_key` record the reference production rate (kg/h) each offer used and the max rate. Use `null` when not stated. The script derives per-tonne figures and flags `BASELINE_MISMATCH`.
9. **Notes.** Every judgment that is not mechanical: unit conventions you resolved (metric vs short tons), keys deliberately left unaligned, scope you treated as not needed.

## Output

Write `RUN_DIR/comparison/alignment.json` conforming to the schema. Then run:

```bash
python3 SKILL_DIR/scripts/build_matrix.py --run-dir RUN_DIR
```

Fix any schema error it reports. Read the printed totals and the `parity.csv` for rows flagged `UNIT_MISMATCH_AFTER_NORMALIZATION` or `NOT_STATED` that are actually aliasing errors on your side, and fix the aliases. Return at most 10 lines to the Admin: offers aligned, alias count, mandatory options, cost adders priced vs unpriced, branches, baseline mismatches.

## Never

* Invent a price, a quantity or an FX rate.
* Drop an exclusion because it is "usually" small.
* Change a finding. If you think a finding is wrong, say so in `notes`; the Admin decides.
