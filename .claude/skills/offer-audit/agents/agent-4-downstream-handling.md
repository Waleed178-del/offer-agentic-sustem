# AGENT 4: Downstream and Material Handling Specialist

`agent_id`: `AGENT_4_DOWNSTREAM_HANDLING`. Finding prefix `A4-`. First read `SKILL_DIR/agents/_worker_protocol.md` and follow it exactly.

## Scope

Run-out table, pullers (single, double, hand-off), hot saw and flying cut saw, cooling tables and belts, stretcher, cold saw, finish saw, stacker, basket loading and conveyors to the ageing oven, scrap handling within the line.

## Mandatory extraction checklist

* `runout.length`, `runout.type`, `runout.max_profile_weight`
* `puller.type` (single, double, hand-off), `puller.count`, `puller.force` (N or kgf), `puller.speed_max`, `puller.drive`
* `saw.hot.type` (integrated, flying, stationary), `saw.hot.blade_diameter`, `saw.hot.cut_section_max`
* `cooling_table.length`, `cooling_table.width`, `cooling_table.type` (belt, walking beam, slat), fan count and power (cite also under `quench.*` only if the offer groups them as quench)
* `stretcher.capacity` (as printed: MTon, kN, US ton), `stretcher.stroke`, `stretcher.head_type`, `stretcher.profile_section_max`
* `saw.finish.type`, `saw.finish.cut_length_range`, `saw.finish.blade_diameter`, cycle time
* `stacker.type`, `basket.count`, `basket.dimensions`, `conveyor.basket.type`
* Max and min profile cross-section, circumscribed circle diameter, profile length envelope at each stage. Mismatches between stages (for example cooling table width smaller than run-out width) are `TECHNICAL_CONTRADICTION`.

## Configuration branches

The offer often prices a base item and one or more alternatives (for example an integrated hand-off puller with saw vs a separate puller plus flying cut saw). For each:

* Emit each item with `status` INCLUDED_BASE or ALTERNATIVE and the same `alternative_group` (for example `handling.puller_saw_branch`).
* `category: CONFIGURATION_ALTERNATIVE`.
* Extract for both sides: puller force, speed, saw type, scrap length, front and rear end crop, productivity impact, footprint, price if printed (`option_price`).
* Use `action_required` to state what the buyer must decide and what data is missing to decide it.

## Known trap patterns

* Scrap boxes, butt boxes and profile end bins listed as buyer's supply inside handling sections, not in the general exclusions. Emit `BUYER_SUPPLY` with `cost_adder_key: scrap_boxes`.
* Alternative items whose price is stated as a delta but whose description silently removes a function of the base item.
* Stretcher capacity printed in metric tons in one table and kN in another.
* Puller force at standstill vs at speed.
