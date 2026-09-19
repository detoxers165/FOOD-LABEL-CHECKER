# FSSAI Label Checker

A regulation engine that checks a food product's ingredients, additives and
lab measurements against FSSAI regulations, and an adapter layer that turns
raw label text (eventually OCR output) into the engine's input format.

## Architecture

```
label image --(OCR, not yet built)--> raw text
                                          |
                                          v
                              label_pipeline.py  (parses text -> structured payload)
                                          |
                                          v
                       fssai_regulation_engine.py  (judges payload against the rulebook)
                                          |
                                          v
                       fssai_regulatory_programmable_rules.json  (the rulebook, as data)
```

- **`fssai_regulation_engine.py`** — the rule engine. Never guesses: if it
  doesn't have enough information (unknown additive, missing category,
  missing concentration, an unfinished regulation table) it defers to
  `COLUMN`/`UNKNOWN` rather than asserting compliant or non-compliant.
- **`fssai_regulatory_programmable_rules.json`** — the rulebook, as data.
  Every rule carries a `source` citing the regulation/section it came
  from. This is the file that grows as we digitize more of the gazette —
  the engine code should rarely need to change for that.
- **`label_pipeline.py`** — turns label text into the engine's input shape.
  The OCR step (`ocr_extract_text`) is currently a stub; everything after
  it is real and tested.
- **`tools/generate_contaminant_prohibition_rules.py`** — a generator
  script that produced most of the current `CONTAMINANT_LIMIT` rules from
  transcribed regulation tables. Kept in the repo as the reference pattern
  for adding the next batch (e.g. the insecticide residue table) — write
  structured Python data, generate rule dicts, merge into the JSON, rather
  than hand-typing hundreds of JSON entries.
- **`tests/`** — regression tests. Run these before and after any change
  to the engine or the rulebook.

## Full-Stack Architecture

- **Frontend (`src/`)**: React 19 + Vite single-page application with dark medical-tech design system. Features drag-and-drop label image upload, mobile camera capture, direct text/ingredient input with sample presets, and comprehensive analysis results dashboard.
- **Backend API (`backend_api.py`)**: FastAPI service connecting PaddleOCR, Legal Metrology compliance engine, and FSSAI regulation engine to HTTP endpoints.
- **Rules Engine (`regulation/`)**: Programmable rulebook and adapter validating INS additives, contaminants, and statutory warnings.

## Running the Application

### 1. Start the Backend API
```bash
source .venv311/bin/activate
pip install -r requirements.txt
python backend_api.py
# Running on http://127.0.0.1:8000
```

### 2. Start the Frontend Dev Server
```bash
npm install
npm run dev
# Running on http://127.0.0.1:5173
```

### API Endpoints
- `GET  /api/health` — Connectivity check and diagnostics.
- `POST /api/scan` — Multipart image upload; runs PaddleOCR, Legal Metrology audit, and FSSAI check.
- `POST /api/analyze-text` — JSON `{ "text": "..." }`; checks ingredients and INS additives.

## Running tests

```bash
pytest tests/ -v
```

## Known gaps (see CONTRIBUTING.md for the full backlog)

- OCR is not wired in (`label_pipeline.ocr_extract_text` is a stub).
- Category resolution (product name → FSSAI category code) is not wired
  in (`label_pipeline.resolve_category` is a stub).
- The insecticide residue table (FSS Contaminants Regulations, 2011,
  §2.3.1 — ~149 rows) has not been digitized yet.
- The Food Additives Regulations (Appendix A permission/limit tables)
  have not been digitized yet — only a handful of illustrative
  `ADDITIVE_PERMISSION` rows exist so far.
- Several qualitative (non-numeric) prohibitions from the Prohibition
  Regulations aren't encoded — the engine doesn't yet have a rule type
  for "must contain X" mandates or ingredient-adulteration checks.

## Working on the rulebook

Numeric limits and category scopes in `fssai_regulatory_programmable_rules.json`
should always be traceable to a specific regulation section — see
`source` on any existing rule for the expected format. Changes to this
file should go through the same PR review as code changes; see
CONTRIBUTING.md.

