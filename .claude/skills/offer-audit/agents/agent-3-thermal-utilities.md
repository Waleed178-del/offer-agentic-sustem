# AGENT 3: Thermal, Combustion and Utilities Specialist

`agent_id`: `AGENT_3_THERMAL_UTILITIES`. Finding prefix `A3-`. First read `SKILL_DIR/agents/_worker_protocol.md` and follow it exactly.

## Scope

Plant utility data tables, log or billet furnace (gas or induction), billet heaters, quench (water, mist, intensive air), ageing oven, die ovens, container heating, any burner, fan, heater or cooling water consumer, and site design conditions.

## Mandatory extraction checklist

**Plant utility tables** (usually a dedicated section near the front)
* `utilities.electrical.installed_power`, `utilities.electrical.absorbed_power`, supply voltage and frequency
* `utilities.natural_gas.max_flow`, `utilities.natural_gas.avg_flow`, supply pressure
* `utilities.compressed_air.max_flow`, `utilities.compressed_air.avg_flow`, pressure, quality class
* `utilities.cooling_water.max_flow`, `utilities.cooling_water.avg_flow`, inlet temperature, delta T
* `utilities.site.ambient_temp_max`, `utilities.site.ambient_temp_min`, altitude, humidity
* Every blank cell in these tables: `MISSING_DATA` quoting the row label, `financial_impact: MEDIUM` unless it blocks sizing a major utility (then HIGH).

**Furnace**
* `furnace.type`, `furnace.capacity` (kg/h at stated billet size and temperature), `furnace.billet_temp`
* `furnace.gas_specific_consumption` (Nm3/t) and the production rate it refers to
* `furnace.gas_flow_max` (Nm3/h). Look in the P&ID or gas train schematic as well as text.
* `furnace.burner.count`, `furnace.burner.power`, heat recovery, emissions (NOx)
* `furnace.temperature_uniformity`, taper heating capability

**Quench and cooling**
* `quench.type`, `quench.fan.count`, `quench.fan.unit_power`, `quench.fan_power_total`, water flow if any, length

**Ageing oven**
* `ageing_oven.capacity` (baskets or kg per batch), `ageing_oven.burner_power`, `ageing_oven.gas_flow`, `ageing_oven.temperature`, `ageing_oven.uniformity`, `ageing_oven.cycle_time`

**Die ovens**
* `die_oven.count`, `die_oven.chambers`, `die_oven.power` (per oven and total), `die_oven.temperature`

## Bottom-up reconstruction (Admin rule R4)

When a plant-level utility value is blank, sum the sub-equipment values you extracted:

```bash
python3 SKILL_DIR/scripts/normalize_units.py sum "120 Nm3/h" "430 Nm3/h"
```

Emit a `DERIVED_ESTIMATE` finding with the same `item_key` and `attribute` as the `MISSING_DATA` finding, `evidence_type: DERIVED`, `derivation.method` stating exactly which consumers were summed and which were unknown, `input_finding_ids`, and the tool stdout. State in `action_required` that this is a lower bound if any consumer had no value. If no inputs exist, emit `NOT_DERIVABLE`.

## Baseline discipline

Consumption figures are only comparable at a stated production rate. For every consumption value record the reference rate (for example "reference consumption at 2,000 kg/h" vs "max capacity 4,000 kg/h"). Emit it as a separate finding `furnace.reference_rate` or `utilities.reference_rate` so Agent 6 can normalize. If the document never states the reference rate, emit `MISSING_DATA` for it.

## Known trap patterns

* Utility summary table blank while the values sit in sub-equipment pages and P&IDs.
* Gas flow on a schematic only. Cite `evidence_type: SCHEMATIC` from the `.vlm.md` transcription.
* Specific consumption quoted at an optimistic reference rate, not at the line's design rate.
* Fan power quoted as installed, not absorbed, or per fan only.
* "Typical" or "approx." consumption: status `PRELIMINARY`, never a guarantee unless a guarantee section says so.
