# Domain Taxonomy and Canonical Keys

## Document Map domains and owners

| Domain | Owner | Typical sections |
|---|---|---|
| GENERAL | Agent 5 | Cover, highlights, general description, layout overview |
| COMMERCIAL | Agent 5 | Price, payment, delivery, validity, warranty |
| UTILITIES | Agent 3 | Plant utility data, site conditions |
| FEEDING | Agent 2 | Log loader, log shear, billet transfer, shuttles |
| FURNACE | Agent 3 | Log or billet furnace, induction heater |
| PRESS | Agent 2 | Extrusion press main body |
| HYDRAULICS | Agent 2 | Power pack, pumps, motors, oil system |
| TOOLING | Agent 2 | Container, stem, die holder, dies |
| QUENCH | Agent 3 | Water, mist or air quench |
| HANDLING | Agent 4 | Run-out, pullers, hot saw |
| STRETCHER | Agent 4 | Stretcher |
| SAW | Agent 4 | Finish saw, cold saw |
| CONVEYOR | Agent 4 | Stackers, baskets, conveyors to ageing |
| AGEING | Agent 3 | Ageing oven |
| DIE_OVEN | Agent 3 | Die ovens |
| ELECTRICAL | Agent 5 | Panels, cabling, drives scope |
| AUTOMATION | Agent 5 | PLC, HMI, MES, Level 2 |
| SAFETY | Agent 5 | Fences, scanners, CE, risk assessment |
| SCOPE_SPLIT | Agent 5 | Supplier vs buyer matrices, exclusions |
| OPTIONS | Agent 5 | Option lists and prices (domain agents read their own options too via secondary routing) |
| SERVICES | Agent 5 | Erection, supervision, commissioning, training |
| OTHER | Agent 5 | Anything else |

`route_sections.py` also sends a section to Agents 2, 3 or 4 as SECONDARY when its title matches their keywords. Agent 5 always reads everything.

## Canonical item keys

Use these exactly. Attribute narrows the key (for example `attribute: 7in`, `attribute: max`, `attribute: per_pump`). If nothing fits use `x.<subsystem>.<vendor_term>`.

**Commercial**: `commercial.headline_price`, `commercial.incoterm`, `commercial.validity`, `commercial.payment_terms`, `commercial.delivery_time`, `commercial.warranty`, `commercial.liquidated_damages`, `commercial.price_escalation`

**Scope**: `scope.field_cabling`, `scope.safety_fencing`, `scope.safety_devices`, `scope.foundations_civil`, `scope.erection_labour`, `scope.supervision`, `scope.commissioning`, `scope.hydraulic_oil`, `scope.piping_utilities`, `scope.scrap_boxes`, `scope.spare_parts`, `scope.training`, `scope.transport`

**Utilities**: `utilities.electrical.installed_power`, `utilities.electrical.absorbed_power`, `utilities.electrical.supply`, `utilities.natural_gas.max_flow`, `utilities.natural_gas.avg_flow`, `utilities.natural_gas.pressure`, `utilities.compressed_air.max_flow`, `utilities.compressed_air.avg_flow`, `utilities.compressed_air.pressure`, `utilities.cooling_water.max_flow`, `utilities.cooling_water.avg_flow`, `utilities.cooling_water.inlet_temp`, `utilities.site.ambient_temp_max`, `utilities.site.ambient_temp_min`, `utilities.reference_rate`, `utilities.reference_profile`

**Feeding**: `feeding.billet.diameter`, `feeding.billet.length_max`, `feeding.billet.length_min`, `feeding.log.length`, `feeding.shear.type`, `feeding.shear.force`, `feeding.<equipment>.drive` (for example `feeding.horizontal_shuttle.drive`)

**Furnace**: `furnace.type`, `furnace.capacity`, `furnace.billet_temp`, `furnace.gas_specific_consumption`, `furnace.gas_flow_max`, `furnace.burner.count`, `furnace.burner.power`, `furnace.reference_rate`, `furnace.taper_heating`, `furnace.nox`

**Press**: `press.main_force`, `press.side_force`, `press.total_force`, `press.specific_pressure`, `press.dead_cycle_time`, `press.ram_speed.extrusion`, `press.ram_speed.return`, `press.stroke`, `press.design`, `press.container.diameter`, `press.container.length`, `press.container.heating_power`, `press.bolster_shear`

**Hydraulics**: `hydraulics.pump.count`, `hydraulics.pump.model`, `hydraulics.pump.unit_power`, `hydraulics.main_motor.starting`, `hydraulics.installed_power`, `hydraulics.oil_volume`, `hydraulics.working_pressure`, `hydraulics.energy_saving` (VFD and similar), `hydraulics.cooling`

**Tooling**: `tooling.die_diameter`, `tooling.die_length`, `tooling.die_holder_dimensions`, `tooling.compatibility`, `tooling.set` (for supplied tool sets)

**Quench**: `quench.type`, `quench.fan.count`, `quench.fan.unit_power`, `quench.fan_power_total`, `quench.water_flow`, `quench.length`

**Handling**: `runout.length`, `runout.type`, `puller.type`, `puller.count`, `puller.force`, `puller.speed_max`, `puller.drive`, `saw.hot.type`, `saw.hot.blade_diameter`, `cooling_table.length`, `cooling_table.width`, `cooling_table.type`, `stretcher.capacity`, `stretcher.stroke`, `saw.finish.type`, `saw.finish.cut_length_range`, `stacker.type`, `basket.count`, `basket.dimensions`, `conveyor.basket.type`, `handling.profile_envelope`

**Ageing oven**: `ageing_oven.capacity`, `ageing_oven.burner_power`, `ageing_oven.gas_flow`, `ageing_oven.temperature`, `ageing_oven.uniformity`, `ageing_oven.cycle_time`

**Die ovens**: `die_oven.count`, `die_oven.chambers`, `die_oven.power`, `die_oven.temperature`

**Line level**: `line.productivity`, `line.recovery`, `line.profile_range`, `line.alloys`, `line.layout_length`

## Alternative groups (examples)

`handling.puller_saw_branch` integrated hand-off puller with saw vs separate puller plus flying saw. `hydraulics.starting_branch` softstarters vs VFD energy saving. `press.container_branch` base container vs additional container.
