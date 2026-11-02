# Red-Flag Lexicon and Trap Catalogue

The machine lexicon lives in `config/lexicon.json` and is applied by `prescan.py`. Extend it with vendor-language terms (Italian, German, French, Chinese) when the offer is not in English. This page is the human catalogue Agent 5 reasons with.

## Phrase families

| Family | Phrases | Default finding |
|---|---|---|
| Exclusion | not included, excluded, does not include, out of scope, not part of supply, escluso, nicht enthalten | HIDDEN_CAPEX_EXCLUSION |
| Buyer supply | buyer's supply, customer will supply, by others, by customer, a cura del cliente, bauseits | BUYER_SUPPLY |
| Option | optional, option, upon request, not quoted, extra price, at additional cost | OPTIONAL_ITEM |
| Alternative | alternatively, in place of, instead of | CONFIGURATION_ALTERNATIVE |
| Preliminary | preliminary, indicative, budgetary, approx., estimated, TBD, TBC, to be confirmed, subject to, for reference only | status PRELIMINARY |
| Guarantee | guaranteed, warranty, liquidated damages, penalty, performance test | PERFORMANCE_GUARANTEE |
| Services | erection, supervision, commissioning, foundations, civil works, first filling, cabling, raceways, fences, scrap boxes, training, spare parts, transport | check scope split |
| Corruption | #VALORE!, #VALUE!, #REF!, #DIV/0!, #N/A, #NOME?, Error! Reference source not found | DATA_CORRUPTION |

## Trap catalogue (patterns proven on extrusion line offers)

1. **Promise in highlights, option in bill of materials.** Introduction says the line runs two billet diameters. The second container and tooling are in the Options section. Rule R5.
2. **Binding constraint inside a drawing.** Buyer's existing tool envelope or die holder dimension appears only in a CAD title block or layout callout. Agent 1 transcribes, Agent 2 cites as DRAWING.
3. **Blank utility summary, values scattered.** Plant utility table has empty flow rows. Furnace gas flow appears on a P&ID, ageing oven gas flow in its own section. Rule R4 bottom-up.
4. **Electrical exclusion on the last page.** Field cabling and raceways excluded in the electrical scope note at the end of the document.
5. **Safety as buyer supply.** Fences, doors, light barriers, laser scanners, safety locks assigned to the customer, often with a brand to be used.
6. **Labour and civil in a services paragraph.** Foundations, erection labour, oil first fill excluded in the press section rather than in general exclusions.
7. **Scrap boxes repeated in several sections.** Each instance is a separate buyer cost.
8. **Table vs narrative drive type.** Table says pneumatic, text says electric motor. Different utility demand, different maintenance.
9. **Max capacity vs reference consumption.** Capacity at 4,000 kg/h, consumption quoted at 2,000 kg/h. Not comparable without normalization.
10. **Spreadsheet errors in imperial columns.** `#VALORE!` cells in converted unit columns. Recover from the metric column, never trust the imperial one.
11. **Energy saving as an option.** VFD drive system priced separately while the base uses softstarters. Compare OPEX in View 3.
12. **Dead cycle time without definition.** Quoted for the smallest container or excluding container sealing.
