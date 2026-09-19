# ============================================================
# GENERAL FOOD LABEL EXTRACTOR - V1
# ============================================================
#
# Input:
#     product_reader_v10.py result JSON
#
# Output:
#     clean standardized product data
#
# IMPORTANT:
# - Does NOT read the image again.
# - Does NOT replace the OCR reader.
# - Does NOT invent missing values.
# - Keeps source/evidence/confidence.
# - Generic for packaged food products.
#
# Pipeline:
#
# V10 READER
#     ↓
# product_result.json
#     ↓
# EXTRACTOR
#     ↓
# normalized product data
#     ↓
# future compliance engine
#
# ============================================================

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)

    value = value.replace(
        "\u00a0",
        " "
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def unique_list(values):
    result = []

    for value in values:
        if value is None:
            continue

        value = clean_text(value)

        if not value:
            continue

        if value not in result:
            result.append(value)

    return result


# ============================================================
# CONFIDENCE
# ============================================================

def entry_confidence(entry):
    """
    Calculate a conservative confidence from whatever
    confidence information the reader supplied.
    """

    if not isinstance(
        entry,
        dict
    ):
        return 0.0

    values = []

    for key in (
        "label_confidence",
        "value_confidence",
        "confidence"
    ):

        value = safe_float(
            entry.get(key)
        )

        if value is not None:
            values.append(value)

    if not values:
        return 0.0

    return round(
        sum(values) / len(values),
        4
    )


# ============================================================
# TEXT / NUMBER NORMALIZATION
# ============================================================

def normalize_quantity(value):
    """
    Convert examples like:

        28g
        28 g
        0.5 kg
        500 ml

    into:

        {
            "value": 28,
            "unit": "g",
            "display": "28 g"
        }
    """

    if not value:
        return None

    text = clean_text(
        value
    )

    pattern = re.search(
        r"(\d+(?:[.,]\d+)?)\s*"
        r"(mg|g|kg|mcg|ug|ml|l|ltr|litre|liter|cl)"
        r"\b",
        text,
        re.IGNORECASE
    )

    if not pattern:
        return None

    number_text = (
        pattern.group(1)
        .replace(
            ",",
            "."
        )
    )

    try:
        number = float(
            number_text
        )
    except Exception:
        return None

    unit = pattern.group(
        2
    ).lower()

    unit_map = {
        "gm": "g",
        "gms": "g",
        "kg": "kg",
        "kgs": "kg",
        "ml": "mL",
        "mls": "mL",
        "l": "L",
        "ltr": "L",
        "litre": "L",
        "liter": "L",
        "cl": "cL",
        "mg": "mg",
        "mcg": "mcg",
        "ug": "mcg",
    }

    unit = unit_map.get(
        unit,
        unit
    )

    if number.is_integer():
        display_number = str(
            int(number)
        )
    else:
        display_number = (
            f"{number:g}"
        )

    return {
        "value": number,
        "unit": unit,
        "display":
            f"{display_number} {unit}"
    }


# ============================================================
# PRICE NORMALIZATION
# ============================================================

def normalize_price(value):
    """
    Converts:

        Rs 10.00
        ₹10
        INR 20

    into a structured price.
    """

    if not value:
        return None

    text = clean_text(
        value
    )

    # Reject unit sale price expressions.
    if re.search(
        r"\busp\b",
        text,
        re.IGNORECASE
    ):
        return None

    if re.search(
        r"\bper\b",
        text,
        re.IGNORECASE
    ):
        return None

    if re.search(
        r"/\s*[a-zA-Z]",
        text
    ):
        return None

    match = re.search(
        r"(?:₹|rs\.?|inr)"
        r"\s*"
        r"(\d+(?:,\d{3})*(?:\.\d{1,2})?)",
        text,
        re.IGNORECASE
    )

    if not match:

        # Bare number is allowed only when the
        # reader has already identified it as MRP.
        match = re.fullmatch(
            r"\s*(\d+(?:\.\d{1,2})?)\s*",
            text
        )

        if not match:
            return None

    number_text = (
        match.group(1)
        .replace(
            ",",
            ""
        )
    )

    try:
        amount = float(
            number_text
        )
    except Exception:
        return None

    return {
        "amount": amount,
        "currency": "INR",
        "display": f"₹{amount:.2f}"
    }


# ============================================================
# DATE NORMALIZATION
# ============================================================

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12
}


def normalize_year(year):
    year = int(year)

    if year < 100:
        if year >= 50:
            return 1900 + year

        return 2000 + year

    return year


def normalize_date(value):
    """
    Supports common package date formats:

        30JUL2026
        30 JUL 2026
        30/07/2026
        30-07-2026
        07/2026
    """

    if not value:
        return None

    text = clean_text(
        value
    )

    # Remove spaces between date components only
    # for parsing.
    compact = re.sub(
        r"\s+",
        "",
        text
    )

    # --------------------------------------------------------
    # DDMMMYYYY
    # --------------------------------------------------------

    match = re.fullmatch(
        r"(\d{1,2})"
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
        r"(\d{2,4})",
        compact,
        re.IGNORECASE
    )

    if match:

        day = int(
            match.group(1)
        )

        month = MONTHS[
            match.group(2).lower()
        ]

        year = normalize_year(
            match.group(3)
        )

        try:

            date = datetime(
                year,
                month,
                day
            )

            return {
                "iso":
                    date.strftime(
                        "%Y-%m-%d"
                    ),
                "original":
                    text
            }

        except ValueError:

            return None

    # --------------------------------------------------------
    # DD/MM/YYYY or DD-MM-YYYY
    # --------------------------------------------------------

    match = re.fullmatch(
        r"(\d{1,2})"
        r"[./-]"
        r"(\d{1,2})"
        r"[./-]"
        r"(\d{2,4})",
        compact
    )

    if match:

        day = int(
            match.group(1)
        )

        month = int(
            match.group(2)
        )

        year = normalize_year(
            match.group(3)
        )

        try:

            date = datetime(
                year,
                month,
                day
            )

            return {
                "iso":
                    date.strftime(
                        "%Y-%m-%d"
                    ),
                "original":
                    text
            }

        except ValueError:

            return None

    # --------------------------------------------------------
    # YYYY/MM/DD
    # --------------------------------------------------------

    match = re.fullmatch(
        r"(\d{4})"
        r"[./-]"
        r"(\d{1,2})"
        r"[./-]"
        r"(\d{1,2})",
        compact
    )

    if match:

        year = int(
            match.group(1)
        )

        month = int(
            match.group(2)
        )

        day = int(
            match.group(3)
        )

        try:

            date = datetime(
                year,
                month,
                day
            )

            return {
                "iso":
                    date.strftime(
                        "%Y-%m-%d"
                    ),
                "original":
                    text
            }

        except ValueError:

            return None

    # --------------------------------------------------------
    # MM/YYYY or MM-YYYY
    # --------------------------------------------------------

    match = re.fullmatch(
        r"(\d{1,2})"
        r"[/-]"
        r"(\d{2,4})",
        compact
    )

    if match:

        month = int(
            match.group(1)
        )

        year = normalize_year(
            match.group(2)
        )

        if 1 <= month <= 12:

            return {
                "iso":
                    f"{year:04d}-{month:02d}",
                "original":
                    text,
                "precision":
                    "month"
            }

    return None


# ============================================================
# LICENSE NORMALIZATION
# ============================================================

def normalize_license(
    value
):
    if not value:
        return None

    digits = re.sub(
        r"\D",
        "",
        str(value)
    )

    if not digits:
        return None

    return digits


# ============================================================
# BATCH NORMALIZATION
# ============================================================

def normalize_batch(
    value
):

    if not value:
        return None

    value = clean_text(
        value
    )

    value = value.strip(
        " :.-"
    )

    if not value:
        return None

    if len(value) > 30:
        return None

    return value


# ============================================================
# GENERIC TEXT FIELD
# ============================================================

def normalize_text_field(
    value
):

    if not value:
        return None

    value = clean_text(
        value
    )

    if value in {
        ":",
        "-",
        ".",
        "N/A",
        "NA",
        "None",
        "Unknown"
    }:

        return None

    return value


# ============================================================
# SOURCE ENTRY
# ============================================================

def make_source(
    entry,
    value
):

    source = {
        "value":
            value,
        "source_text":
            entry.get(
                "label"
            ),
        "evidence":
            entry.get(
                "evidence",
                []
            ),
        "confidence":
            entry_confidence(
                entry
            ),
    }

    if entry.get(
        "label_box"
    ) is not None:

        source[
            "label_box"
        ] = entry[
            "label_box"
        ]

    if entry.get(
        "value_box"
    ) is not None:

        source[
            "value_box"
        ] = entry[
            "value_box"
        ]

    return source


# ============================================================
# EXTRACT ONE FIELD
# ============================================================

def extract_field(
    product_information,
    field,
    normalizer
):

    entry = product_information.get(
        field
    )

    if not isinstance(
        entry,
        dict
    ):
        return None

    raw_value = entry.get(
        "value"
    )

    normalized = normalizer(
        raw_value
    )

    if normalized is None:
        return None

    return make_source(
        entry,
        normalized
    )


# ============================================================
# EXTRACT FSSAI
# ============================================================

def extract_fssai(
    product_information
):

    entry = product_information.get(
        "fssai_license"
    )

    if not isinstance(
        entry,
        dict
    ):
        return {
            "values": [],
            "evidence": []
        }

    values = []

    for raw in entry.get(
        "values",
        []
    ):

        normalized = normalize_license(
            raw
        )

        if (
            normalized
            and normalized not in values
        ):

            values.append(
                normalized
            )

    evidence = []

    for item in entry.get(
        "evidence",
        []
    ):

        if isinstance(
            item,
            dict
        ):

            evidence.append(
                {
                    "value":
                        normalize_license(
                            item.get(
                                "value"
                            )
                        ),

                    "evidence":
                        item.get(
                            "evidence",
                            []
                        ),

                    "confidence":
                        safe_float(
                            item.get(
                                "confidence"
                            )
                        ),

                    "box":
                        item.get(
                            "box"
                        )
                }
            )

    return {
        "values": values,
        "evidence": evidence
    }


# ============================================================
# EXTRACT SECTIONS
# ============================================================

def extract_section(
    sections,
    name
):

    section = sections.get(
        name
    )

    if not isinstance(
        section,
        dict
    ):
        return None

    content = section.get(
        "content"
    )

    if isinstance(
        content,
        list
    ):

        text = " ".join(
            clean_text(x)
            for x in content
            if clean_text(x)
        )

    else:

        text = clean_text(
            section.get(
                "text"
            )
        )

    if not text:
        return None

    return {
        "text":
            text,

        "heading":
            section.get(
                "heading"
            ),

        "confidence":
            safe_float(
                section.get(
                    "confidence"
                )
            ),

        "evidence":
            content
            if isinstance(
                content,
                list
            )
            else [text]
    }


# ============================================================
# EXTRACT CONTACTS
# ============================================================

def extract_contacts(
    contacts
):

    if not isinstance(
        contacts,
        dict
    ):

        contacts = {}

    phones = unique_list(
        contacts.get(
            "phones",
            []
        )
    )

    emails = unique_list(
        contacts.get(
            "emails",
            []
        )
    )

    websites = unique_list(
        contacts.get(
            "websites",
            []
        )
    )

    return {

        "phones":
            phones,

        "emails":
            emails,

        "websites":
            websites
    }


# ============================================================
# EXTRACT NUTRITION
# ============================================================

def normalize_nutrition_value(
    value
):

    if value is None:
        return None

    value = clean_text(
        value
    )

    if not value:
        return None

    return value


def extract_nutrition(
    nutrition
):

    if not isinstance(
        nutrition,
        dict
    ):

        return {}

    result = {}

    for nutrient, entry in (
        nutrition.items()
    ):

        if not isinstance(
            entry,
            dict
        ):
            continue

        values = entry.get(
            "values",
            {}
        )

        normalized_values = {}

        if isinstance(
            values,
            dict
        ):

            for key, value in (
                values.items()
            ):

                normalized = (
                    normalize_nutrition_value(
                        value
                    )
                )

                if normalized is not None:

                    normalized_values[
                        key
                    ] = normalized

        else:

            value = (
                normalize_nutrition_value(
                    entry.get(
                        "value"
                    )
                )
            )

            if value is not None:

                normalized_values[
                    "value"
                ] = value

        if not normalized_values:
            continue

        result[
            nutrient
        ] = {

            "values":
                normalized_values,

            "basis":
                entry.get(
                    "basis"
                ),

            "confidence":
                safe_float(
                    entry.get(
                        "confidence"
                    )
                ),

            "evidence":
                entry.get(
                    "evidence",
                    []
                )
        }

    return result


# ============================================================
# CONFLICT DETECTION
# ============================================================

def collect_conflicts(
    product_information
):

    conflicts = {}

    for field, entry in (
        product_information.items()
    ):

        if not isinstance(
            entry,
            dict
        ):
            continue

        values = []

        primary = entry.get(
            "value"
        )

        if primary:
            values.append(
                clean_text(
                    primary
                )
            )

        additional = entry.get(
            "additional_values",
            []
        )

        if isinstance(
            additional,
            list
        ):

            for value in additional:

                if value:

                    values.append(
                        clean_text(
                            value
                        )
                    )

        values = unique_list(
            values
        )

        if len(values) > 1:

            conflicts[
                field
            ] = values

    return conflicts


# ============================================================
# QUALITY ANALYSIS
# ============================================================

def field_status(
    result
):

    required_for_extraction = [
        "net_quantity",
        "mrp",
        "batch_number",
        "manufacturing_date",
        "expiry_date",
        "fssai_licenses",
        "manufacturer",
        "ingredients"
    ]

    status = {}

    for field in (
        required_for_extraction
    ):

        value = result.get(
            field
        )

        if value is None:

            status[
                field
            ] = "not_detected"

        elif value == []:

            status[
                field
            ] = "not_detected"

        else:

            status[
                field
            ] = "detected"

    return status


def extraction_quality(
    result
):

    detected = 0
    total = 0
    warnings = []

    fields = field_status(
        result
    )

    for field, status in (
        fields.items()
    ):

        total += 1

        if status == "detected":
            detected += 1

    conflicts = result.get(
        "conflicts",
        {}
    )

    if conflicts:

        warnings.append(
            "Conflicting values were found. "
            "Review the conflicts section."
        )

    for field_name in (
        "mrp",
        "net_quantity",
        "manufacturing_date",
        "expiry_date",
        "batch_number"
    ):

        source = result.get(
            "_sources",
            {}).get(
                field_name
            )

        if source:

            confidence = safe_float(
                source.get(
                    "confidence"
                )
            )

            if (
                confidence is not None
                and confidence < 0.70
            ):

                warnings.append(
                    f"{field_name} has "
                    f"low source confidence."
                )

    return {

        "fields_detected":
            detected,

        "fields_considered":
            total,

        "coverage":
            round(
                detected / total,
                3
            )
            if total
            else 0.0,

        "warnings":
            unique_list(
                warnings
            )
    }


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract(
    reader_json
):

    product_information = (
        reader_json.get(
            "product_information",
            {}
        )
    )

    sections = (
        reader_json.get(
            "sections",
            {}
        )
    )

    nutrition = (
        reader_json.get(
            "nutrition",
            {}
        )
    )

    contacts = (
        reader_json.get(
            "contacts",
            {}
        )
    )

    output = {

        "schema_version":
            "extractor_v1",

        "source_image":
            reader_json.get(
                "source_image"
            ),

        "product_name":
            None,

        "brand":
            None,

        "net_quantity":
            extract_field(
                product_information,
                "net_quantity",
                normalize_quantity
            ),

        "mrp":
            extract_field(
                product_information,
                "mrp",
                normalize_price
            ),

        "batch_number":
            extract_field(
                product_information,
                "batch_number",
                normalize_batch
            ),

        "manufacturing_date":
            extract_field(
                product_information,
                "manufacturing_date",
                normalize_date
            ),

        "expiry_date":
            extract_field(
                product_information,
                "expiry_date",
                normalize_date
            ),

        "fssai_licenses":
            extract_fssai(
                product_information
            ),

        "manufacturer":
            extract_field(
                product_information,
                "manufacturer",
                normalize_text_field
            ),

        "marketed_by":
            extract_field(
                product_information,
                "marketed_by",
                normalize_text_field
            ),

        "ingredients":
            extract_section(
                sections,
                "ingredients"
            ),

        "allergen_information":
            extract_section(
                sections,
                "allergen"
            ),

        "storage_instructions":
            extract_section(
                sections,
                "storage"
            ),

        "customer_care":
            extract_field(
                product_information,
                "customer_care",
                normalize_text_field
            ),

        "email":
            extract_field(
                product_information,
                "email",
                normalize_text_field
            ),

        "website":
            extract_field(
                product_information,
                "website",
                normalize_text_field
            ),

        "nutrition":
            extract_nutrition(
                nutrition
            ),

        "contacts":
            extract_contacts(
                contacts
            ),

        "conflicts":
            collect_conflicts(
                product_information
            )
    }

    # --------------------------------------------------------
    # Keep internal source objects for quality calculations.
    # Remove them before final JSON.
    # --------------------------------------------------------

    output["_sources"] = {

        "net_quantity":
            output[
                "net_quantity"
            ],

        "mrp":
            output[
                "mrp"
            ],

        "batch_number":
            output[
                "batch_number"
            ],

        "manufacturing_date":
            output[
                "manufacturing_date"
            ],

        "expiry_date":
            output[
                "expiry_date"
            ]
    }

    quality = extraction_quality(
        output
    )

    output["extraction_quality"] = quality

    # --------------------------------------------------------
    # Remove internal source data.
    # --------------------------------------------------------

    output.pop(
        "_sources",
        None
    )

    return output


# ============================================================
# DISPLAY
# ============================================================

def display_result(
    result
):

    print()
    print(
        "=" * 70
    )

    print(
        "EXTRACTED PRODUCT DATA"
    )

    print(
        "=" * 70
    )

    simple_fields = [
        "product_name",
        "brand",
        "manufacturer",
        "marketed_by",
        "customer_care",
        "email",
        "website"
    ]

    for field in simple_fields:

        print(
            f"{field:25} : "
            f"{result.get(field)}"
        )

    print()

    print(
        f"{'net_quantity':25} : "
        f"{result.get('net_quantity')}"
    )

    print(
        f"{'mrp':25} : "
        f"{result.get('mrp')}"
    )

    print(
        f"{'batch_number':25} : "
        f"{result.get('batch_number')}"
    )

    print(
        f"{'manufacturing_date':25} : "
        f"{result.get('manufacturing_date')}"
    )

    print(
        f"{'expiry_date':25} : "
        f"{result.get('expiry_date')}"
    )

    print()

    print(
        "FSSAI LICENSES:"
    )

    for value in result[
        "fssai_licenses"
    ][
        "values"
    ]:

        print(
            "  ",
            value
        )

    print()

    print(
        "NUTRITION:"
    )

    for nutrient, data in (
        result[
            "nutrition"
        ].items()
    ):

        print(
            f"  {nutrient:22} : "
            f"{data.get('values')}"
        )

    print()

    print(
        "SECTIONS:"
    )

    for field in (
        "ingredients",
        "allergen_information",
        "storage_instructions"
    ):

        data = result.get(
            field
        )

        if data:

            print()
            print(
                f"[{field}]"
            )

            print(
                "  "
                + data[
                    "text"
                ][:800]
            )

    print()

    print(
        "=" * 70
    )

    print(
        "EXTRACTION QUALITY"
    )

    print(
        "=" * 70
    )

    quality = result[
        "extraction_quality"
    ]

    print(
        "Fields detected :",
        quality[
            "fields_detected"
        ]
    )

    print(
        "Fields checked  :",
        quality[
            "fields_considered"
        ]
    )

    print(
        "Coverage        :",
        quality[
            "coverage"
        ]
    )

    if quality[
        "warnings"
    ]:

        print()

        for warning in quality[
            "warnings"
        ]:

            print(
                "WARNING:",
                warning
            )

    conflicts = result[
        "conflicts"
    ]

    if conflicts:

        print()

        print(
            "=" * 70
        )

        print(
            "CONFLICTS"
        )

        print(
            "=" * 70
        )

        for field, values in (
            conflicts.items()
        ):

            print(
                f"{field}:"
            )

            for value in values:

                print(
                    "  ",
                    value
                )

    print()


# ============================================================
# INPUT FILE DISCOVERY
# ============================================================

def find_default_input(
    directory
):

    preferred = [
        "product_result.json",
        "arranged_result.json"
    ]

    for name in preferred:

        path = os.path.join(
            directory,
            name
        )

        if os.path.isfile(
            path
        ):

            return path

    candidates = []

    for filename in os.listdir(
        directory
    ):

        if (
            filename.endswith(
                "_result.json"
            )
            and
            not filename.endswith(
                "_extracted.json"
            )
        ):

            candidates.append(
                os.path.join(
                    directory,
                    filename
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=os.path.getmtime,
        reverse=True
    )

    return candidates[0]


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "General packaged-food "
            "label extractor"
        )
    )

    parser.add_argument(
        "input",
        nargs="?",
        help=(
            "Reader result JSON. "
            "Example: output/image6_result.json"
        )
    )

    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "Output JSON path"
        )
    )

    args = parser.parse_args()

    project_root = os.path.dirname(
        os.path.dirname(
            os.path.abspath(
                __file__
            )
        )
    )

    output_dir = os.path.join(
        project_root,
        "output"
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Input selection
    # --------------------------------------------------------

    input_file = args.input

    if input_file:

        if not os.path.isabs(
            input_file
        ):

            input_file = os.path.abspath(
                input_file
            )

    else:

        input_file = find_default_input(
            output_dir
        )

    if not input_file:

        print(
            "ERROR: No reader JSON found."
        )

        print(
            "Give the JSON path explicitly."
        )

        return 1

    if not os.path.isfile(
        input_file
    ):

        print(
            "ERROR: File not found:"
        )

        print(
            input_file
        )

        return 1

    print()
    print(
        "=" * 70
    )

    print(
        "GENERAL FOOD LABEL EXTRACTOR V1"
    )

    print(
        "=" * 70
    )

    print()

    print(
        "Input:"
    )

    print(
        input_file
    )

    print()

    # --------------------------------------------------------
    # Read JSON
    # --------------------------------------------------------

    try:

        with open(
            input_file,
            "r",
            encoding="utf-8"
        ) as file:

            reader_json = json.load(
                file
            )

    except Exception as exc:

        print(
            "ERROR: Could not read JSON."
        )

        print(
            str(exc)
        )

        return 1

    # --------------------------------------------------------
    # Extract
    # --------------------------------------------------------

    print(
        "Extracting and normalizing..."
    )

    result = extract(
        reader_json
    )

    # --------------------------------------------------------
    # Output file
    # --------------------------------------------------------

    if args.output:

        output_file = args.output

        if not os.path.isabs(
            output_file
        ):

            output_file = os.path.abspath(
                output_file
            )

    else:

        stem = os.path.splitext(
            os.path.basename(
                input_file
            )
        )[0]

        output_file = os.path.join(
            output_dir,
            stem + "_extracted.json"
        )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=2,
            ensure_ascii=False
        )

    print()

    print(
        "Extraction complete."
    )

    print(
        "Output:"
    )

    print(
        output_file
    )

    display_result(
        result
    )

    return 0


if __name__ == "__main__":

    sys.exit(
        main()
    )