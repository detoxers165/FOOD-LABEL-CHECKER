"""
Adapter between OCR label output and RegulationEngine.

The adapter's job is translation only:
    OCR result -> structured regulatory input -> RegulationEngine

It does NOT decide whether an ingredient is safe or compliant.

Important principles:
- Preserve original OCR/label wording.
- Only create additive records when an explicit INS code is present.
- Never invent an additive identity from vague ingredient wording.
- Do not invent a regulatory category.
- Preserve OCR evidence/confidence when available.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engine import RegulationEngine


# ---------------------------------------------------------------------------
# INS extraction
# ---------------------------------------------------------------------------

INS_PATTERN = re.compile(
    r"INS\s*[:-]?\s*(\d+\s*(?:\([ivx]+\))?)",
    re.IGNORECASE,
)


def extract_ins_numbers(text: str) -> List[str]:
    """Extract explicit INS codes such as 211, 100(i), or 133."""
    return [
        match.group(1).replace(" ", "")
        for match in INS_PATTERN.finditer(text or "")
    ]


# ---------------------------------------------------------------------------
# Plain-text ingredient extraction
# ---------------------------------------------------------------------------

def extract_ingredient_list(text: str) -> List[str]:
    """
    Extract an ingredient section from plain OCR text.

    This remains available for simple text-based tests.
    Structured OCR should use build_payload_from_ocr().
    """
    if not text:
        return []

    match = re.search(
        r"ingredients?\s*[:-]?\s*(.+)",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return []

    section = match.group(1)

    # Stop at obvious following label sections.
    section = re.split(
        r"\n\s*(?:nutritional|nutrition|allergen|best before|net qty|"
        r"net quantity|storage|manufactured|manufacturing)",
        section,
        flags=re.IGNORECASE,
    )[0]

    parts = [part.strip(" .\n") for part in section.split(",")]
    return [part for part in parts if part]


# ---------------------------------------------------------------------------
# Additive extraction
# ---------------------------------------------------------------------------

def build_additives_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Build additive records ONLY from explicit INS declarations.

    Ordinary ingredients are not treated as additives merely because
    they occur inside the ingredient list.
    """
    additives: List[Dict[str, Any]] = []

    for match in INS_PATTERN.finditer(text or ""):
        ins = match.group(1).replace(" ", "")

        # Find a small piece of surrounding text to preserve the
        # label's declared wording without pretending we know more
        # than the OCR actually tells us.
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 40)
        context = text[start:end].strip()

        additives.append(
            {
                "declared_name": context,
                "ins": ins,
                "amount": None,
                "unit": None,
            }
        )

    return additives


def build_additives(
    ingredients: List[str],
) -> List[Dict[str, Any]]:
    """
    Backwards-compatible additive builder for a parsed ingredient list.

    Only ingredients containing an explicit INS code become additives.
    """
    additives: List[Dict[str, Any]] = []

    for item in ingredients:
        matches = list(INS_PATTERN.finditer(item))

        for match in matches:
            ins = match.group(1).replace(" ", "")

            declared_name = INS_PATTERN.sub("", item).strip(" ()-[]")

            additives.append(
                {
                    "declared_name": declared_name or item,
                    "ins": ins,
                    "amount": None,
                    "unit": None,
                }
            )

    return additives


# ---------------------------------------------------------------------------
# Category resolution
# -------------------------------------------------------------------------

FSSAI_CATEGORY_ALIASES = {
    "15.1": "SNACKS_SAVOURIES_15_1",
    "PROPRIETARY FOOD - NAMKEEN (MIXTURES) - 15.1": "SNACKS_SAVOURIES_15_1",
}


def _normalize_category_text(value: str) -> str:
    """Normalize category wording for deterministic alias matching."""
    return re.sub(r"\s+", " ", value.strip()).upper()


def resolve_category(
    product_name: str,
    category_hint: Optional[str] = None,) -> Optional[str]:
    """
    Resolve an OCR/label category only when an explicit validated
    FSSAI category alias exists.

    Unknown categories remain unresolved.
    """
    if not category_hint:
        return None

    normalized = _normalize_category_text(category_hint)

    # Exact canonical category already supplied.
    if normalized in FSSAI_CATEGORY_ALIASES:
        return FSSAI_CATEGORY_ALIASES[normalized]

    return None


# ---------------------------------------------------------------------------
# Existing plain-text payload path
# ---------------------------------------------------------------------------

def build_payload(
    label_text: str,
    product_name: str,
    category_hint: Optional[str] = None,
    measurements: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build RegulationEngine input from plain label text."""
    ingredients_raw = extract_ingredient_list(label_text)

    return {
        "product": {
            "declared_name": product_name,
            "resolved_category": resolve_category(
                product_name,
                category_hint,
            ),
            "ingredients": ingredients_raw,
        },
        "additives": build_additives(ingredients_raw),
        "measurements": measurements or [],
    }


# ---------------------------------------------------------------------------
# Structured OCR -> RegulationEngine adapter
# ---------------------------------------------------------------------------

def _get_ocr_ingredient_text(ocr_result: Dict[str, Any]) -> str:
    """Get the ingredient text from the structured OCR result."""
    sections = ocr_result.get("sections") or {}
    ingredients = sections.get("ingredients") or {}

    return ingredients.get("text") or ingredients.get("content") or ""


def _get_ocr_category(ocr_result: Dict[str, Any]) -> Optional[str]:
    """
    Extract category wording from the OCR result.

    The current OCR output places the category after the allergen text,
    so we search all structured section text rather than assuming there
    is a dedicated category section.

    This returns the OCR wording as-is and does not claim that it is
    already a normalized executable FSSAI category.
    """
    category_pattern = re.compile(
        r"(PROPRIETARY\s+FOOD\s*-\s*[^.\n]+?-\s*\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    sections = ocr_result.get("sections") or {}

    for section in sections.values():
        if not isinstance(section, dict):
            continue

        for field in ("text", "content", "heading"):
            value = section.get(field)

            if not isinstance(value, str):
                continue

            match = category_pattern.search(value)

            if match:
                return match.group(1).strip()

    return None


def _extract_product_name(ocr_result: Dict[str, Any]) -> Optional[str]:
    """Extract product name if the OCR output contains one."""
    product_information = ocr_result.get("product_information") or {}

    product_name = product_information.get("product_name")

    if isinstance(product_name, dict):
        return product_name.get("value") or product_name.get("text")

    if isinstance(product_name, str):
        return product_name

    return None


def _extract_ins_additives_with_evidence(
    ingredient_text: str,
    ocr_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Extract explicit INS codes and preserve the declared wording.

    For example:

        COLOURS [INS 100(i), INS 133]

    becomes two additive records:

        COLOURS -> 100(i)
        COLOURS -> 133

    No additive identity is assigned here. The RegulationEngine performs
    identity normalization from the regulatory rule file.
    """
    additives: List[Dict[str, Any]] = []

    raw_regions = ocr_result.get("raw_ocr") or []

    # Look for an ingredient/function phrase immediately before an
    # INS bracket group, e.g.:
    #
    #   COLOURS [INS 100(i), INS 133]
    #
    bracket_pattern = re.compile(
        r"([A-Za-z][A-Za-z\s-]{0,60}?)\s*"
        r"\[\s*(INS\s*[^]]+)\]",
        re.IGNORECASE,
    )

    matched_ins_codes = set()

    for match in bracket_pattern.finditer(ingredient_text or ""):
        declared_name = match.group(1).strip(" ,.;:-")
        ins_text = match.group(2)

        for ins_match in INS_PATTERN.finditer(ins_text):
            ins = ins_match.group(1).replace(" ", "")
            matched_ins_codes.add(ins.lower())

            evidence: List[Dict[str, Any]] = []

            for region in raw_regions:
                region_text = str(region.get("text") or "")

                if ins.lower() in region_text.lower():
                    evidence.append(
                        {
                            "text": region_text,
                            "confidence": region.get("confidence"),
                            "box": region.get("box"),
                        }
                    )

            additives.append(
                {
                    "declared_name": declared_name,
                    "ins": ins,
                    "amount": None,
                    "unit": None,
                    "ocr_evidence": evidence,
                }
            )

    # Fallback: if an INS code exists outside a bracketed colour/additive
    # expression, preserve it rather than silently dropping it.
    for match in INS_PATTERN.finditer(ingredient_text or ""):
        ins = match.group(1).replace(" ", "")

        if ins.lower() in matched_ins_codes:
            continue

        evidence: List[Dict[str, Any]] = []

        for region in raw_regions:
            region_text = str(region.get("text") or "")

            if ins.lower() in region_text.lower():
                evidence.append(
                    {
                        "text": region_text,
                        "confidence": region.get("confidence"),
                        "box": region.get("box"),
                    }
                )

        additives.append(
            {
                "declared_name": "UNSPECIFIED",
                "ins": ins,
                "amount": None,
                "unit": None,
                "ocr_evidence": evidence,
            }
        )

    return additives


def build_payload_from_ocr(
    ocr_result: Dict[str, Any],
    category_hint: Optional[str] = None,
    measurements: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Convert the structured output of the real OCR pipeline into the
    exact product_data shape expected by RegulationEngine.check().
    """
    ingredient_text = _get_ocr_ingredient_text(ocr_result)

    product_name = _extract_product_name(ocr_result)

    ocr_category = _get_ocr_category(ocr_result)

    # IMPORTANT:
    # The OCR category is preserved as evidence, but is not automatically
    # treated as an executable normalized FSSAI category.
    resolved_category = resolve_category(
        product_name or "",
        category_hint or ocr_category,
    )

    additives = _extract_ins_additives_with_evidence(
        ingredient_text,
        ocr_result,
    )

    payload: Dict[str, Any] = {
        "product": {
            "declared_name": product_name,
            "resolved_category": resolved_category,
            "ingredients": [ingredient_text] if ingredient_text else [],
            "ocr_category": ocr_category,
        },
        "additives": additives,
        "measurements": measurements or [],
    }

    return payload


# ---------------------------------------------------------------------------
# Engine entry points
# ---------------------------------------------------------------------------

def check_label(
    label_text: str,
    product_name: str,
    rules_file: str | Path,
    category_hint: Optional[str] = None,
    measurements: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """End-to-end plain-text path."""
    engine = RegulationEngine(rules_file)

    payload = build_payload(
        label_text,
        product_name,
        category_hint,
        measurements,
    )

    return engine.check(payload)


def check_ocr_result(
    ocr_result: Dict[str, Any],
    rules_file: str | Path,
    category_hint: Optional[str] = None,
    measurements: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    End-to-end structured OCR path.

    OCR result in -> RegulationEngine result out.
    """
    engine = RegulationEngine(rules_file)

    payload = build_payload_from_ocr(
        ocr_result,
        category_hint,
        measurements,
    )

    result = engine.check(payload)

    # Preserve traceability information outside the engine's regulatory
    # decision structure.
    result["ocr_trace"] = {
        "source_image": ocr_result.get("source_image"),
        "quality": ocr_result.get("quality"),
        "preprocessing": ocr_result.get("preprocessing"),
        "raw_ocr_preserved": bool(ocr_result.get("raw_ocr")),
        "ingredient_text": _get_ocr_ingredient_text(ocr_result),
        "ocr_category": _get_ocr_category(ocr_result),
    }

    return result


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the FSSAI regulation engine against OCR JSON."
    )

    parser.add_argument(
        "ocr_json",
        nargs="?",
        help="Path to structured OCR result JSON.",
    )

    parser.add_argument(
        "--rules",
        default=str(Path(__file__).resolve().parent / "rules.json"),
        help="Path to regulation rules JSON.",
    )

    args = parser.parse_args()

    if args.ocr_json:
        with open(args.ocr_json, encoding="utf-8") as f:
            ocr_result = json.load(f)

        result = check_ocr_result(
            ocr_result,
            args.rules,
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        sample_text = """
        Ingredients: Water, Sugar, Carbon Dioxide,
        Sodium Benzoate (INS 211),
        Citric Acid (INS 330),
        Colour (INS 102)
        """

        result = check_label(
            sample_text,
            product_name="Fizzy Cola",
            rules_file=Path(__file__).resolve().parent / "rules.json",
            category_hint="CARBONATED_BEVERAGES",
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )
