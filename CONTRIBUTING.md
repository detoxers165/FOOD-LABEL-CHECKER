# Contributing

## Code changes

- Add or update tests under `tests/` for any behavior change in
  `fssai_regulation_engine.py` or `label_pipeline.py`.
- Run `pytest tests/ -v` before opening a PR. CI will also run this on
  every push (see `.github/workflows/tests.yml`).

## Rulebook changes (fssai_regulatory_programmable_rules.json)

This file encodes claims about what the law actually says. Treat it with
the same rigor as code, plus one more requirement: **every rule must be
traceable to a specific regulation, section, and (where relevant) table
row** via its `source` field. Rules copied from memory rather than a
primary source should be clearly marked as a placeholder (see existing
`"note"` fields containing "placeholder" / "verify against current
gazette") and must not be treated as production-ready until verified.

**PRs that touch this file need a second reviewer** who checks the new
entries against the actual gazette/notification text, not just against
the PR description. A rule that's wrong is worse than a rule that's
missing — a missing rule shows up as an honest "needs review" deferral;
a wrong rule shows up as false confidence.

When adding a large batch of rules from a table-heavy regulation section
(e.g. the insecticide residue table, or the Food Additives Appendix A
tables), don't hand-type the JSON. Follow the pattern in
`tools/generate_contaminant_prohibition_rules.py`:
1. Transcribe the table into a structured Python list of tuples.
2. Generate rule dicts from it with a small helper function.
3. Merge into the rules file, checking for `rule_id` collisions.
4. Add tests that exercise the category-scoping logic, not just "a rule
   fired" — the bug most likely to hide here is a category mismatch or a
   rule quietly shadowing another rule with the same `check.field`.

## Current backlog

- [ ] OCR integration in `label_pipeline.ocr_extract_text`
- [ ] Category resolution (`label_pipeline.resolve_category`) — needs a
      product-name → FSSAI-category classifier or lookup table
- [ ] Insecticide residue table (FSS Contaminants Regs 2011, §2.3.1, ~149 rows)
- [ ] Food Additives Regulations Appendix A (additive permission/limit tables)
- [ ] Qualitative prohibitions from the Prohibition Regulations (added
      water in milk, mandatory salt iodization, Kesari gram restrictions,
      etc.) — needs a new rule type; don't force these into
      `PRODUCT_STANDARD_NUMERIC` or `CONTAMINANT_LIMIT`, they aren't numeric
- [ ] Base-ingredient allowlist (water, sugar, salt, flour, ...) so the
      UI doesn't flag every ordinary ingredient as "identity unknown"
