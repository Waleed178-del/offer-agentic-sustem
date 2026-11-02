# Admin Adjudication Template

Write this into `RUN_DIR/comparison/admin_adjudication.md`. `render_report.py` embeds it at the top of the report. Keep it under 600 words. Every claim cites a clarification id, finding id or matrix row.

```markdown
### Verdict

<One paragraph. Which offer is technically compliant, which is commercially lowest on a scope-adjusted basis, and whether that conclusion survives the unpriced items. State confidence as a number with its basis, for example "Confidence 0.6: 9 adders unpriced, headline price of OFFER_B not stated.">

### Decision drivers

1. <driver, cite rows or ids>
2. <driver>
3. <driver>

### Hard truths

* <unavoidable fact, tradeoff or hidden cost the buyer must accept or price>
* <what this audit cannot know until vendors answer the P1 items>

### Before contract signature

* <P1 clarifications per vendor, by id>
* <cost book entries the buyer must fill to close landed cost>
* <buyer decisions on configuration branches>
```

Rules: no number you did not read from `matrix.json`. No recommendation that depends on an UNPRICED line without saying so. If the gate finalized with unresolved loop items, say which and why they matter.
