import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from schemas.compliance import COMPLIANCE_STATUSES

NULL_LIKE_VALUES = {
    "",
    "n/a",
    "na",
    "-",
    "null",
    "none",
    "not found",
    "unknown",
    "unavailable",
}


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_null(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()

        if cleaned.lower() in NULL_LIKE_VALUES:
            return None

        return cleaned

    return value


def normalize_text(value: Any) -> str | None:
    value = normalize_null(value)

    if value is None:
        return None

    return str(value).strip() or None


def normalize_list(values: Any) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        values = [values]

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = normalize_text(value)

        if normalized is None:
            continue

        key = normalized.casefold()

        if key not in seen:
            seen.add(key)
            result.append(normalized)

    return result


def normalize_status(value: Any) -> str:
    normalized = str(value or "").strip().upper()

    if normalized not in COMPLIANCE_STATUSES:
        return "NEEDS_REVIEW"

    return normalized


def normalize_date(value: Any) -> str | None:
    value = normalize_null(value)

    if value is None:
        return None

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    raw = str(value).strip()

    iso_candidates = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
    ]

    for fmt in iso_candidates:
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def normalize_number(value: Any) -> float | None:
    value = normalize_null(value)

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, int | float):
        return float(value)

    text = str(value).strip()
    text = text.replace(",", "")

    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return None

    try:
        return float(Decimal(match.group(0)))
    except InvalidOperation:
        return None


def normalize_money(
    value: Any,
    *,
    default_currency: str = "INR",
) -> dict[str, Any] | None:
    value = normalize_null(value)

    if value is None:
        return None

    if isinstance(value, dict):
        number = normalize_number(
            value.get("value", value.get("amount"))
        )
        currency = normalize_text(
            value.get("currency")
        ) or default_currency

        if number is None:
            return {
                "value": None,
                "currency": currency,
            }

        return {
            "value": number,
            "currency": currency.upper(),
        }

    text = str(value)
    currency = default_currency

    if "₹" in text or "rs" in text.lower() or "inr" in text.lower():
        currency = "INR"

    number = normalize_number(text)

    return {
        "value": number,
        "currency": currency,
    }


def normalize_quantity(value: Any) -> dict[str, Any] | None:
    value = normalize_null(value)

    if value is None:
        return None

    if isinstance(value, dict):
        number = normalize_number(
            value.get("value", value.get("amount"))
        )
        unit = normalize_text(value.get("unit"))

        return {
            "value": number,
            "unit": unit,
        }

    text = str(value)
    number = normalize_number(text)

    if number is None:
        return {
            "value": None,
            "unit": None,
        }

    unit_match = re.search(
        r"(mg|kg|ml|l|g|mcg|kcal|cal|%)",
        text,
        flags=re.IGNORECASE,
    )

    unit = unit_match.group(1).lower() if unit_match else None

    return {
        "value": number,
        "unit": unit,
    }


def normalize_dynamic_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    return {
        str(key): normalize_null(item)
        for key, item in value.items()
    }


def normalize_product(product: Any) -> dict[str, Any]:
    product = product if isinstance(product, dict) else {}

    known_keys = {
        "brand",
        "product_name",
        "category",
        "variant",
        "net_quantity",
        "unit",
        "mrp",
        "unit_sale_price",
        "batch_number",
        "manufacturing_date",
        "expiry_date",
        "best_before",
        "fssai_license_number",
        "manufacturer",
        "packer",
        "marketer",
        "country_of_origin",
        "additional_fields",
    }

    normalized = {
        "brand": normalize_text(product.get("brand")),
        "product_name": normalize_text(product.get("product_name")),
        "category": normalize_text(product.get("category")),
        "variant": normalize_text(product.get("variant")),
        "net_quantity": normalize_quantity(
            product.get("net_quantity")
        ),
        "unit": normalize_text(product.get("unit")),
        "mrp": normalize_money(product.get("mrp")),
        "unit_sale_price": normalize_money(
            product.get("unit_sale_price")
        ),
        "batch_number": normalize_text(product.get("batch_number")),
        "manufacturing_date": normalize_date(
            product.get("manufacturing_date")
        ),
        "expiry_date": normalize_date(product.get("expiry_date")),
        "best_before": normalize_text(product.get("best_before")),
        "fssai_license_number": normalize_text(
            product.get("fssai_license_number")
        ),
        "manufacturer": normalize_text(product.get("manufacturer")),
        "packer": normalize_text(product.get("packer")),
        "marketer": normalize_text(product.get("marketer")),
        "country_of_origin": normalize_text(
            product.get("country_of_origin")
        ),
        "additional_fields": normalize_dynamic_mapping(
            product.get("additional_fields")
        ),
    }

    for key, value in product.items():
        if key not in known_keys:
            normalized["additional_fields"][key] = normalize_null(value)

    return normalized


def normalize_analysis_output(output: dict[str, Any]) -> dict[str, Any]:
    """
    Normalizes the adapter contract without modifying or discarding
    the original reader output. The caller stores the original output
    separately in raw_extraction.
    """
    output = output if isinstance(output, dict) else {}

    product = normalize_product(output.get("product"))

    ingredients = normalize_list(output.get("ingredients"))

    allergens_input = output.get("allergens")
    allergens_input = (
        allergens_input
        if isinstance(allergens_input, dict)
        else {}
    )

    allergens = {
        "contains": normalize_list(
            allergens_input.get("contains")
        ),
        "may_contain": normalize_list(
            allergens_input.get("may_contain")
        ),
    }

    nutrition_input = output.get("nutrition")
    nutrition_input = (
        nutrition_input
        if isinstance(nutrition_input, dict)
        else {}
    )

    nutrition_known_keys = {
        "energy",
        "protein",
        "carbohydrate",
        "total_sugars",
        "added_sugars",
        "dietary_fibre",
        "total_fat",
        "saturated_fat",
        "trans_fat",
        "sodium",
        "salt",
        "cholesterol",
        "other_nutrients",
    }

    nutrition = {
        key: normalize_quantity(nutrition_input.get(key))
        for key in nutrition_known_keys
        if key != "other_nutrients"
    }

    nutrition["other_nutrients"] = normalize_dynamic_mapping(
        nutrition_input.get("other_nutrients")
    )

    for key, value in nutrition_input.items():
        if key not in nutrition_known_keys:
            nutrition["other_nutrients"][key] = normalize_quantity(value)

    contact = output.get("contact_information")
    contact = contact if isinstance(contact, dict) else {}

    contact_information = {
        "consumer_care": normalize_text(
            contact.get("consumer_care")
        ),
        "phone": normalize_text(contact.get("phone")),
        "email": normalize_email(contact["email"])
        if normalize_text(contact.get("email"))
        else None,
        "website": normalize_text(contact.get("website")),
        "address": normalize_text(contact.get("address")),
    }

    label_declarations = normalize_dynamic_mapping(
        output.get("label_declarations")
    )

    compliance = output.get("compliance")
    compliance = compliance if isinstance(compliance, dict) else {}

    compliance_result = {
        "overall_status": normalize_status(
            compliance.get("overall_status")
        ),
        "violations": [],
        "passed_checks": [],
        "needs_review": [],
        "not_applicable": compliance.get("not_applicable")
        if isinstance(compliance.get("not_applicable"), list)
        else [],
        "not_checked": compliance.get("not_checked")
        if isinstance(compliance.get("not_checked"), list)
        else [],
    }

    for item in compliance.get("violations", []) or []:
        if isinstance(item, dict):
            normalized_item = dict(item)
            normalized_item["status"] = normalize_status(
                normalized_item.get("status")
            )
            compliance_result["violations"].append(normalized_item)

    for item in compliance.get("passed_checks", []) or []:
        if isinstance(item, dict):
            normalized_item = dict(item)
            normalized_item["status"] = "PASS"
            compliance_result["passed_checks"].append(normalized_item)

    for item in compliance.get("needs_review", []) or []:
        if isinstance(item, dict):
            normalized_item = dict(item)
            normalized_item["status"] = "NEEDS_REVIEW"
            compliance_result["needs_review"].append(normalized_item)

    metadata = output.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}

    return {
        "product": product,
        "ingredients": ingredients,
        "allergens": allergens,
        "nutrition": nutrition,
        "contact_information": contact_information,
        "label_declarations": label_declarations,
        "compliance": compliance_result,
        "metadata": normalize_dynamic_mapping(metadata),
    }


def compute_compliance_summary(compliance: dict[str, Any]) -> dict[str, Any]:
    violations = compliance.get("violations", [])
    passed_checks = compliance.get("passed_checks", [])
    needs_review = compliance.get("needs_review", [])
    not_applicable = compliance.get("not_applicable", [])
    not_checked = compliance.get("not_checked", [])

    return {
        "overall_status": normalize_status(
            compliance.get("overall_status")
        ),
        "total_rules_checked": (
            len(violations)
            + len(passed_checks)
            + len(needs_review)
            + len(not_applicable)
            + len(not_checked)
        ),
        "passed": len(passed_checks),
        "failed": len(violations),
        "needs_review": len(needs_review),
        "not_applicable": len(not_applicable),
        "not_checked": len(not_checked),
    }
