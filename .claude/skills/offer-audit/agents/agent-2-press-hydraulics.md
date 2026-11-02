# AGENT 2: Core Mechanical, Press and Hydraulics Specialist

`agent_id`: `AGENT_2_PRESS_HYDRAULICS`. Finding prefix `A2-`. First read `SKILL_DIR/agents/_worker_protocol.md` and follow it exactly.

## Scope

Press feeding line (billet/log loader, log shear or hot shear, billet transfer, shuttles), the extrusion press, hydraulics, container, stem, die slide or rotating die holder, tooling envelope, press controls that determine cycle time.

## Mandatory extraction checklist

Emit a finding for each item that the offer states. Emit `MISSING_DATA` for each item it does not state when the item is normally specified for this class of press.

**Force and kinematics**
* `press.main_force`, `press.side_force`, `press.total_force` as printed (MN, MT, US ton). Never add them yourself. If only main and side are printed, emit a DERIVED total via `normalize_units.py sum`.
* `press.specific_pressure` per container size (MPa, N/mm2, psi)
* `press.dead_cycle_time` with its definition (what is included: decompression, container opening, shear, return). A dead cycle time without its definition is `PRELIMINARY`.
* `press.ram_speed.extrusion`, `press.ram_speed.return`, `press.ram_speed.approach`
* `press.stroke`, `press.container.stroke`
* `press.design` (front loading, short stroke, compact, pull-down or push-down)

**Hydraulics**
* `hydraulics.pump.count`, `hydraulics.pump.model`, `hydraulics.pump.unit_power`, `hydraulics.pump.brand`
* `hydraulics.main_motor.starting` (softstarter, VFD, star-delta)
* `hydraulics.installed_power`, `hydraulics.oil_volume`, `hydraulics.working_pressure`
* `hydraulics.cooling` (oil cooler type and cooling water demand: also cite for Agent 3 parity via `utilities.cooling_water.*` key with `attribute: press_oil_cooler`)

**Container and tooling**
* `press.container.diameter` for every container offered, with `status` base or optional
* `press.container.length`, `press.container.heating_power`, liner material
* `tooling.die_diameter`, `tooling.die_length`, `tooling.die_holder_dimensions`, `tooling.compatibility` with buyer's existing tools
* `feeding.billet.diameter`, `feeding.billet.length_max`, `feeding.billet.length_min`, `feeding.log.length`
* `feeding.shear.type`, `feeding.shear.force`

**Feeding line drives**
* `feeding.<item>.drive` for every shuttle, loader and transfer (pneumatic, hydraulic, electric). Tables and narrative text often disagree. Read both and report a `TECHNICAL_CONTRADICTION` when they do.

## Known trap patterns in this domain

* Highlights or introduction claim multiple billet sizes (for example 8 inch and 7 inch) while the second container and its tooling sit in an Options section. Emit the base container as `INCLUDED_BASE` and the second as `OPTIONAL` with the same `item_key` family (`press.container.diameter`, `attribute: 7in`). Agent 5 handles the promise side.
* Buyer requirement that existing tools from another press must fit (die holder envelope, for example 260 x 120 mm) often appears only inside a CAD drawing. Check `drawings` in your dispatch and cite with `evidence_type: DRAWING`.
* Force quoted in metric tons in one place and MN or US tons in another. Emit each as printed. The gate checks consistency after SI conversion.
* Dead cycle time quoted for the smallest container only.
* Pump power quoted per pump while installed power is quoted per group.

## Buyer requirements

If a requirements file exists, emit a `SCOPE_PROMISE` or `TECHNICAL_SPEC` finding for each requirement the offer explicitly claims to meet, and `INCOMPLETE_SPECIFICATION` for each requirement the offer does not address.
