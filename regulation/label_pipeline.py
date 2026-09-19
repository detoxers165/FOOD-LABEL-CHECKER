"""
Adapter layer between a food label and the RegulationEngine.

This module has exactly one job: turn label content into the
`product_data` dict that RegulationEngine.check() expects. It is the
seam where you'll plug in your real OCR later — everything downstream
(the regulation engine) is already finished and doesn't need to change.

Pipeline:
    label image -> ocr_extract_text()      [stub -- replace with real OCR]
                 -> parse_label_text()      [regex/NLP extraction]
                 -> resolve_category()      [name -> FSSAI category, stub]
                 -> build_payload()         [assembles engine input]
                 -> RegulationEngine.check()
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fssai_regulation_engine import RegulationEngine


# ---------------------------------------------------------------------------
# 1. OCR -- stubbed. Replace this with your real OCR call later; everything
#    else in this file only depends on it returning plain text.
# ---------------------------------------------------------------------------

def ocr_extract_text(image_path: str | Path) -> str:
    """Placeholder OCR step.

    Swap this out for your real OCR reader. The rest of the pipeline only
    needs it to return the label's plain text (ingredient list included).
    """
    raise NotImplementedError(
        "Plug in the real OCR reader here. For now, pass label text "
        "directly to parse_label_text() to test the rest of the pipeline."
    )


# ---------------------------------------------------------------------------
# 2. Extraction -- pull structured signals out of raw label text.
# ---------------------------------------------------------------------------

INS_PATTERN = re.compile(
    r"INS\s*[:\-]?\s*(\d+\s*(?:\([ivx]+\))?)", re.IGNORECASE
)


def extract_ins_numbers(text: str) -> List[str]:
    """Pull INS codes like '211' or '100(i)' out of raw label text."""
    return [m.group(1).replace(" ", "") for m in INS_PATTERN.finditer(text)]


def extract_ingredient_list(text: str) -> List[str]:
    """
    Very rough ingredient-list splitter: looks for an "Ingredients:" section
    and splits on commas. Real OCR text is messy (line breaks mid-word,
    misread characters) -- expect to harden this once real OCR is wired in.
    """
    match = re.search(r"ingredients?\s*[:\-]\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    section = match.group(1)
    # Stop at the next clearly-different label section if present.
    section = re.split(r"\n\s*(nutritional|allergen|best before|net qty)", section, flags=re.IGNORECASE)[0]
    parts = [p.strip(" .\n") for p in section.split(",")]
    return [p for p in parts if p]


def build_additives(ingredients: List[str]) -> List[Dict[str, Any]]:
    """
    Turn parsed ingredient strings into the engine's additive shape.
    `amount`/`unit` are left None on purpose -- concentration isn't printed
    on most Indian packaged-food labels, so the engine will correctly defer
    maximum-level checks rather than guess a number that isn't there.
    """
    additives = []
    for item in ingredients:
        ins_match = INS_PATTERN.search(item)
        ins = ins_match.group(1).replace(" ", "") if ins_match else None
        # Strip the "(INS 211)" annotation back out to get a clean declared name.
        declared_name = INS_PATTERN.sub("", item).strip(" ()-")
        additives.append({
            "declared_name": declared_name or item,
            "ins": ins,
            "amount": None,
            "unit": None,
        })
    return additives


# ---------------------------------------------------------------------------
# 3. Category resolution -- stubbed. This is its own subsystem: a lookup
#    table or a small classifier mapping product name/type -> FSSAI category
#    code. Wire it in when ready; until then resolved_category stays None
#    and the engine correctly flags category-dependent checks as UNKNOWN.
# ---------------------------------------------------------------------------

def resolve_category(product_name: str, category_hint: Optional[str] = None) -> Optional[str]:
    if category_hint:
        return category_hint
    # TODO: replace with a real classifier / lookup table.
    return None


# ---------------------------------------------------------------------------
# 4. Assemble the engine payload.
# ---------------------------------------------------------------------------

def build_payload(
    label_text: str,
    product_name: str,
    category_hint: Optional[str] = None,
    measurements: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    ingredients_raw = extract_ingredient_list(label_text)
    return {
        "product": {
            "declared_name": product_name,
            "resolved_category": resolve_category(product_name, category_hint),
            "ingredients": ingredients_raw,
        },
        "additives": build_additives(ingredients_raw),
        # Lab-report data (contaminants, fat %, etc.) doesn't come from OCR --
        # it's a separate ingestion path. Pass it through if you have it.
        "measurements": measurements or [],
    }


def check_label(
    label_text: str,
    product_name: str,
    rules_file: str | Path,
    category_hint: Optional[str] = None,
    measurements: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """End-to-end: label text in, engine audit result out."""
    engine = RegulationEngine(rules_file)
    payload = build_payload(label_text, product_name, category_hint, measurements)
    return engine.check(payload)


if __name__ == "__main__":
    # Smoke test using text you'd otherwise get from OCR.
    sample_text = """
    Ingredients: Water, Sugar, Carbon Dioxide, Sodium Benzoate (INS 211),
    Citric Acid (INS 330), Colour (INS 102)
    """
    result = check_label(
        sample_text,
        product_name="Fizzy Cola",
        rules_file=Path(__file__).with_name("fssai_regulatory_programmable_rules.json"),
        category_hint="CARBONATED_BEVERAGES",
    )
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
