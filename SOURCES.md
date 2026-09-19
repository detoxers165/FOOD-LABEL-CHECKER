# Source documents

Track which FSSAI gazette notifications have been digitized into
`fssai_regulatory_programmable_rules.json`, and to what extent. Don't
commit the PDFs themselves (see `.gitignore`) — link to where the team
sourced them instead, so anyone can re-verify a rule against the original.

| Regulation | Status | Notes |
|---|---|---|
| FSS (Prohibition and Restrictions on Sales) Regulations, 2011 | Partial | Numeric standards + clean additive bans done (cream fat %, hexane residues, tobacco/nicotine/carbide gas). Qualitative clauses not yet encoded — see CONTRIBUTING.md backlog. |
| FSS (Contaminants, Toxins and Residues) Regulations, 2011 | Mostly done | Metal contaminants (§2.1.1), crop contaminants/natural toxins (§2.2.1), seafood antibiotics (§2.3.2) done. Insecticide residue table (§2.3.1, ~149 rows) not yet done. |
| FSS (Food Products Standards and Food Additives) Regulations, 2011 | Not started | Appendix A additive permission/limit tables — the big one. Only a handful of illustrative placeholder rows exist today; these are explicitly flagged as placeholders in the rules JSON and must be verified before relying on them. |
