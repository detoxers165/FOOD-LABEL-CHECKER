# ============================================================
# GENERAL FOOD LABEL READER - V6
# ============================================================
#
# Generic pipeline:
#
# IMAGE
#   ↓
# PADDLEOCR
#   ↓
# OCR TEXT + BOUNDING BOXES
#   ↓
# VISUAL ROWS
#   ↓
# LOCAL METADATA MATCHING
#   ↓
# SECTION DETECTION
#   ↓
# NUTRITION TABLE RECONSTRUCTION
#   ↓
# STRUCTURED JSON
#
# IMPORTANT:
# No brand-specific coordinates.
# No product-specific assumptions.
# ============================================================

import json
import os
import re
import sys
import statistics
from dataclasses import dataclass
from tkinter import Tk, filedialog


# ============================================================
# PADDLEOCR STARTUP
# ============================================================

os.environ.setdefault(
    "FLAGS_use_mkldnn",
    "0"
)

os.environ.setdefault(
    "FLAGS_enable_pir_api",
    "0"
)

try:

    from paddleocr import PaddleOCR

except Exception as exc:

    print(
        "ERROR: Could not import PaddleOCR."
    )

    print(str(exc))

    sys.exit(1)


# ============================================================
# GENERIC FIELD VOCABULARY
# ============================================================

FIELD_ALIASES = {

    "net_quantity": [
        "net quantity",
        "net qty",
        "net weight",
        "net wt",
        "net content",
        "net contents"
    ],

    "mrp": [
        "maximum retail price",
        "max retail price",
        "maximum retail selling price",
        "mrp"
    ],

    "batch_number": [
        "batch number",
        "batch no",
        "batch no.",
        "batch code",
        "lot number",
        "lot no",
        "lot no.",
        "lot code"
    ],

    "manufacturing_date": [
        "date of manufacture",
        "manufacturing date",
        "manufactured date",
        "mfg date",
        "mfg. date",
        "date of mfg",
        "packed on",
        "packing date"
    ],

    "expiry_date": [
        "expiry date",
        "expiration date",
        "exp date",
        "exp. date",
        "use by",
        "use before",
        "best before"
    ],

    "manufacturer": [
        "manufactured by",
        "manufactured for",
        "manufacturer",
        "mfd by",
        "mfd. by"
    ],

    "marketed_by": [
        "marketed by",
        "marketed for"
    ],

    "customer_care": [
        "customer care",
        "consumer care",
        "customer service",
        "consumer service",
        "contact us",
        "helpline",
        "help line"
    ],

    "email": [
        "email",
        "e-mail"
    ],

    "website": [
        "website",
        "web site"
    ]
}


# ============================================================
# SECTION VOCABULARY
# ============================================================

SECTION_ALIASES = {

    "ingredients": [
        "ingredients",
        "ingredient"
    ],

    "nutrition": [
        "nutrition facts",
        "nutrition information",
        "nutritional information",
        "nutrition"
    ],

    "storage": [
        "storage instructions",
        "storage conditions",
        "storage"
    ],

    "allergen": [
        "allergen advice",
        "allergen information",
        "allergens"
    ]
}


# ============================================================
# NUTRIENTS
# ============================================================

NUTRIENT_ALIASES = [

    ("total carbohydrate", "total_carbohydrate"),
    ("added sugars", "added_sugars"),
    ("total sugars", "total_sugars"),
    ("saturated fat", "saturated_fat"),
    ("trans fat", "trans_fat"),
    ("dietary fibre", "dietary_fibre"),
    ("dietary fiber", "dietary_fiber"),
    ("cholesterol", "cholesterol"),
    ("carbohydrates", "carbohydrate"),
    ("carbohydrate", "carbohydrate"),
    ("protein", "protein"),
    ("total fat", "total_fat"),
    ("polyunsaturated fat", "polyunsaturated_fat"),
    ("monounsaturated fat", "monounsaturated_fat"),
    ("energy", "energy"),
    ("calories", "calories"),
    ("sodium", "sodium"),
    ("potassium", "potassium"),
    ("calcium", "calcium"),
    ("iron", "iron"),
    ("sugars", "sugars"),
    ("fat", "fat"),
    ("salt", "salt"),
    ("fibre", "fibre"),
    ("fiber", "fiber")
]


# ============================================================
# COMMON ALLERGENS
# Used only for recognizing allergen statements.
# ============================================================

ALLERGEN_WORDS = {
    "wheat",
    "gluten",
    "soy",
    "soya",
    "milk",
    "peanut",
    "peanuts",
    "almond",
    "almonds",
    "cashew",
    "cashews",
    "walnut",
    "walnuts",
    "nut",
    "nuts",
    "sesame",
    "mustard",
    "egg",
    "eggs",
    "fish",
    "crustacean",
    "crustaceans",
    "shellfish",
    "sulphite",
    "sulphites",
    "sulfite",
    "sulfites"
}


# ============================================================
# REGION DATA STRUCTURE
# ============================================================

@dataclass
class Region:

    index: int

    text: str

    confidence: float | None

    box: list | None

    x1: float
    y1: float
    x2: float
    y2: float

    cx: float
    cy: float

    width: float
    height: float

    row_id: int = -1


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(value):

    try:
        return float(value)

    except Exception:
        return None


def normalize_text(text):

    text = str(text)

    replacements = {
        "–": "-",
        "—": "-",
        "−": "-",
        "：": ":",
        "’": "'",
        "“": '"',
        "”": '"'
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new
        )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def clean_text(text):

    text = normalize_text(
        text
    ).lower()

    text = re.sub(
        r"^[\s\-\*•·\"']+",
        "",
        text
    )

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def compact_text(text):

    return re.sub(
        r"[^a-z0-9₹%]",
        "",
        clean_text(text)
    )


# ============================================================
# BOX PARSING
# ============================================================

def parse_box(box):

    if box is None:
        return None

    try:

        # PaddleOCR rec_boxes:
        #
        # [x1, y1, x2, y2]
        #

        if (
            isinstance(
                box,
                (list, tuple)
            )
            and len(box) == 4
            and all(
                isinstance(
                    value,
                    (int, float)
                )
                for value in box
            )
        ):

            x1, y1, x2, y2 = map(
                float,
                box
            )

            return (
                min(x1, x2),
                min(y1, y2),
                max(x1, x2),
                max(y1, y2)
            )

        # Polygon format.

        xs = []
        ys = []

        for point in box:

            if (
                isinstance(
                    point,
                    (list, tuple)
                )
                and len(point) >= 2
            ):

                xs.append(
                    float(point[0])
                )

                ys.append(
                    float(point[1])
                )

        if xs and ys:

            return (
                min(xs),
                min(ys),
                max(xs),
                max(ys)
            )

    except Exception:

        pass

    return None


def make_regions(
    ocr_data
):

    regions = []

    for i, raw in enumerate(
        ocr_data.get(
            "regions",
            []
        )
    ):

        text = normalize_text(
            raw.get(
                "text",
                ""
            )
        )

        bounds = parse_box(
            raw.get(
                "box"
            )
        )

        if not text:
            continue

        if bounds is None:
            continue

        x1, y1, x2, y2 = bounds

        regions.append(

            Region(

                index=i,

                text=text,

                confidence=safe_float(
                    raw.get(
                        "confidence"
                    )
                ),

                box=raw.get(
                    "box"
                ),

                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,

                cx=(x1 + x2) / 2,
                cy=(y1 + y2) / 2,

                width=max(
                    1.0,
                    x2 - x1
                ),

                height=max(
                    1.0,
                    y2 - y1
                )
            )
        )

    return regions


# ============================================================
# VISUAL ROW DETECTION
# ============================================================

def build_rows(
    regions
):

    if not regions:
        return []

    ordered = sorted(
        regions,
        key=lambda r: (
            r.cy,
            r.x1
        )
    )

    median_height = statistics.median(
        [
            r.height
            for r in regions
        ]
    )

    tolerance = max(
        4.0,
        min(
            9.0,
            median_height * 0.6
        )
    )

    rows = []

    row_centers = []

    for region in ordered:

        best_row = None

        best_difference = (
            float("inf")
        )

        for row_id, center in enumerate(
            row_centers
        ):

            difference = abs(
                region.cy
                - center
            )

            if (
                difference <= tolerance
                and difference < best_difference
            ):

                best_row = row_id

                best_difference = (
                    difference
                )

        if best_row is None:

            rows.append(
                [region]
            )

            row_centers.append(
                region.cy
            )

        else:

            rows[
                best_row
            ].append(
                region
            )

            row_centers[
                best_row
            ] = (
                sum(
                    r.cy
                    for r in rows[
                        best_row
                    ]
                )
                /
                len(
                    rows[
                        best_row
                    ]
                )
            )

    # Final ordering.

    final = []

    pairs = sorted(
        zip(
            row_centers,
            rows
        ),
        key=lambda item: item[0]
    )

    for row_id, (_, row) in enumerate(
        pairs
    ):

        row.sort(
            key=lambda r: r.x1
        )

        for region in row:
            region.row_id = row_id

        final.append(
            row
        )

    return final


# ============================================================
# LABEL DETECTION
# ============================================================

def alias_match(
    text,
    aliases
):

    normalized = clean_text(
        text
    )

    compact = compact_text(
        text
    )

    best = 0

    for alias in aliases:

        alias_normalized = clean_text(
            alias
        )

        alias_compact = compact_text(
            alias
        )

        if (
            normalized == alias_normalized
            or normalized.startswith(
                alias_normalized + " "
            )
            or normalized.startswith(
                alias_normalized + ":"
            )
            or normalized.startswith(
                alias_normalized + "-"
            )
            or compact == alias_compact
            or compact.startswith(
                alias_compact
            )
        ):

            best = max(
                best,
                len(alias_compact)
            )

    return best


def detect_field(
    text
):

    matches = []

    for field, aliases in (
        FIELD_ALIASES.items()
    ):

        score = alias_match(
            text,
            aliases
        )

        if score:

            matches.append(
                (
                    score,
                    field
                )
            )

    if not matches:
        return None

    return max(
        matches,
        key=lambda x: x[0]
    )[1]


def detect_section(
    text
):

    compact = compact_text(
        text
    )

    for section, aliases in (
        SECTION_ALIASES.items()
    ):

        if alias_match(
            text,
            aliases
        ):

            return section

    # OCR often joins words.

    if compact.startswith(
        "nutritionalinformation"
    ):

        return "nutrition"

    if compact.startswith(
        "nutritionfacts"
    ):

        return "nutrition"

    if compact.startswith(
        "allergenadvice"
    ):

        return "allergen"

    if compact.startswith(
        "storageinstructions"
    ):

        return "storage"

    return None


def looks_like_allergen_statement(
    text
):

    normalized = clean_text(
        text
    )

    starts = (

        normalized.startswith(
            "contains "
        )

        or normalized.startswith(
            "may contain "
        )

        or normalized.startswith(
            "may contains "
        )

        or normalized.startswith(
            "allergen advice"
        )

        or normalized.startswith(
            "allergen information"
        )
    )

    if not starts:
        return False

    compact = compact_text(
        text
    )

    for word in ALLERGEN_WORDS:

        if compact_text(
            word
        ) in compact:

            return True

    return False


# ============================================================
# VALUE EXTRACTION
# ============================================================

DATE_PATTERNS = [

    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",

    r"\b\d{2,4}[./-]\d{1,2}[./-]\d{1,2}\b",

    r"\b\d{1,2}\s*"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"[a-z]*\s*\d{2,4}\b",

    r"\b\d{1,2}"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"\d{2,4}\b"
]


def extract_date(
    text
):

    for pattern in DATE_PATTERNS:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            return match.group(
                0
            )

    return None


def extract_weight(
    text
):

    match = re.search(
        r"\b\d+(?:\.\d+)?\s*"
        r"(?:mg|g|kg|ml|l|litre|liter|cl)\b",
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(
            0
        )

    return None


def extract_price(
    text
):

    value = normalize_text(
        text
    )

    # NEVER accept unit-price / USP expressions.
    if re.search(
        r"\busp\b",
        value,
        re.IGNORECASE
    ):

        return None

    if re.search(
        r"\bper\s+\w+",
        value,
        re.IGNORECASE
    ):

        return None

    if re.search(
        r"/\s*[a-zA-Z]",
        value
    ):

        return None

    # Currency amount.

    match = re.search(
        r"(?:₹|rs\.?|inr)\s*"
        r"\d+(?:,\d{3})*"
        r"(?:\.\d{1,2})?",
        value,
        re.IGNORECASE
    )

    if match:
        return match.group(
            0
        ).strip()

    # Pure numeric value.

    if re.fullmatch(
        r"\s*\d+(?:\.\d{1,2})?\s*",
        value
    ):

        return value.strip()

    return None


def extract_batch(
    text
):

    value = normalize_text(
        text
    ).strip(
        " .:-"
    )

    if not value:
        return None

    if len(value) > 30:
        return None

    if len(value.split()) > 2:
        return None

    if not re.fullmatch(
        r"[A-Za-z0-9]"
        r"[A-Za-z0-9._/-]{3,25}",
        value
    ):

        return None

    # Batch codes normally contain at least one number.

    if not any(
        char.isdigit()
        for char in value
    ):

        return None

    return value


def extract_email(
    text
):

    return re.findall(
        r"\b[A-Z0-9._%+-]+"
        r"@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        text,
        re.IGNORECASE
    )


def extract_website(
    text
):

    values = re.findall(
        r"(?:https?://|www\.)"
        r"[^\s,;]+",
        text,
        re.IGNORECASE
    )

    return [
        value.rstrip(
            ".,;)"
        )
        for value in values
    ]


# ============================================================
# INLINE FIELD VALUES
# ============================================================

def extract_inline_value(
    field,
    text
):

    aliases = sorted(
        FIELD_ALIASES[
            field
        ],
        key=len,
        reverse=True
    )

    normalized = normalize_text(
        text
    )

    for alias in aliases:

        pattern = (
            r"^\s*"
            + re.escape(
                normalize_text(
                    alias
                )
            )
            + r"\s*[:\-]?\s*(.*)$"
        )

        match = re.match(
            pattern,
            normalized,
            re.IGNORECASE
        )

        if not match:
            continue

        rest = match.group(
            1
        ).strip()

        if not rest:
            return None

        if field == "net_quantity":
            return extract_weight(
                rest
            )

        if field == "mrp":
            return extract_price(
                rest
            )

        if field in (
            "manufacturing_date",
            "expiry_date"
        ):

            return extract_date(
                rest
            )

        if field == "batch_number":
            return extract_batch(
                rest
            )

        if field == "email":

            values = extract_email(
                rest
            )

            return (
                values[0]
                if values
                else None
            )

        if field == "website":

            values = extract_website(
                rest
            )

            return (
                values[0]
                if values
                else None
            )

        # Manufacturer etc.
        if re.search(
            r"[A-Za-z0-9]",
            rest
        ):

            return rest

    return None


# ============================================================
# FIELD VALIDATION
# ============================================================

def valid_field_value(
    field,
    text
):

    if not text:
        return False

    if detect_field(
        text
    ) is not None:

        return False

    if detect_section(
        text
    ) is not None:

        return False

    if field == "net_quantity":

        return (
            extract_weight(
                text
            )
            is not None
        )

    if field == "mrp":

        return (
            extract_price(
                text
            )
            is not None
        )

    if field in (
        "manufacturing_date",
        "expiry_date"
    ):

        return (
            extract_date(
                text
            )
            is not None
        )

    if field == "batch_number":

        return (
            extract_batch(
                text
            )
            is not None
        )

    if field == "email":

        return bool(
            extract_email(
                text
            )
        )

    if field == "website":

        return bool(
            extract_website(
                text
            )
        )

    if clean(text) in {
        ":",
        "-",
        "."
    }:

        return False

    return bool(
        re.search(
            r"[A-Za-z0-9]",
            text
        )
    )


# ============================================================
# LOCAL VALUE MATCHING
# ============================================================

def same_row_candidate(
    label,
    candidate,
    field
):

    if label.index == candidate.index:
        return None

    if candidate.index in {
        label.index
    }:

        return None

    if detect_field(
        candidate.text
    ) is not None:

        return None

    if detect_section(
        candidate.text
    ) is not None:

        return None

    # Candidate should be to the right.

    if candidate.x1 < (
        label.x2 - 10
    ):

        return None

    vertical_gap = abs(
        candidate.cy
        -
        label.cy
    )

    tolerance = max(
        label.height,
        candidate.height,
        8
    ) * 1.4

    if vertical_gap > tolerance:
        return None

    horizontal_gap = max(
        0,
        candidate.x1
        -
        label.x2
    )

    if horizontal_gap > max(
        350,
        label.width * 5
    ):

        return None

    if not valid_field_value(
        field,
        candidate.text
    ):

        return None

    score = (

        2000

        - vertical_gap * 15

        - horizontal_gap * 2
    )

    # Strong field-specific preference.

    if field == "mrp":

        if extract_price(
            candidate.text
        ):

            score += 500

    elif field == "net_quantity":

        if extract_weight(
            candidate.text
        ):

            score += 500

    elif field in (
        "manufacturing_date",
        "expiry_date"
    ):

        if extract_date(
            candidate.text
        ):

            score += 500

    elif field == "batch_number":

        if extract_batch(
            candidate.text
        ):

            score += 500

    return score


def below_row_candidate(
    label,
    candidate,
    field
):

    vertical_gap = (
        candidate.y1
        -
        label.y2
    )

    if vertical_gap < -5:
        return None

    if vertical_gap > 80:
        return None

    horizontal_gap = abs(
        candidate.cx
        -
        label.cx
    )

    if horizontal_gap > max(
        140,
        label.width * 2.5
    ):

        return None

    if not valid_field_value(
        field,
        candidate.text
    ):

        return None

    return (
        900
        -
        vertical_gap * 8
        -
        horizontal_gap * 2
    )


def find_field_value(
    label,
    field,
    rows,
    used_indices
):

    candidates = []

    # --------------------------------------------------------
    # SAME ROW
    # --------------------------------------------------------

    if (
        label.row_id >= 0
        and label.row_id < len(rows)
    ):

        for candidate in rows[
            label.row_id
        ]:

            if candidate.index in used_indices:
                continue

            score = same_row_candidate(
                label,
                candidate,
                field
            )

            if score is not None:

                candidates.append(
                    (
                        score,
                        candidate
                    )
                )

    if candidates:

        return max(
            candidates,
            key=lambda x: x[0]
        )

    # --------------------------------------------------------
    # IMMEDIATE ROW BELOW
    #
    # We intentionally search ONLY one row below.
    # This prevents:
    #
    # MFG DATE -> USE BY DATE
    #
    # --------------------------------------------------------

    next_row = (
        label.row_id + 1
    )

    if next_row < len(rows):

        for candidate in rows[
            next_row
        ]:

            if candidate.index in used_indices:
                continue

            score = below_row_candidate(
                label,
                candidate,
                field
            )

            if score is not None:

                candidates.append(
                    (
                        score,
                        candidate
                    )
                )

    if candidates:

        return max(
            candidates,
            key=lambda x: x[0]
        )

    return None


# ============================================================
# METADATA EXTRACTION
# ============================================================

def extract_metadata(
    regions,
    rows
):

    result = {}

    used = set()

    for region in regions:

        field = detect_field(
            region.text
        )

        if field is None:
            continue

        # ----------------------------------------------------
        # FSSAI is handled separately.
        # ----------------------------------------------------

        if field == "fssai_license":
            continue

        # ----------------------------------------------------
        # Simple fields
        # ----------------------------------------------------

        value = extract_inline_value(
            field,
            region.text
        )

        value_region = None

        if value is None:

            found = find_field_value(
                region,
                field,
                rows,
                used
            )

            if found:

                _, candidate = found

                value = (
                    extract_inline_value(
                        field,
                        candidate.text
                    )
                    or
                    (
                        candidate.text
                        if valid_field_value(
                            field,
                            candidate.text
                        )
                        else None
                    )
                )

                if value is not None:

                    value_region = (
                        candidate
                    )

                    used.add(
                        candidate.index
                    )

        entry = {

            "value": value,

            "label":
                region.text,

            "confidence":
                region.confidence,

            "box":
                region.box,

            "evidence": [
                region.text
            ]
        }

        if value_region is not None:

            entry[
                "value_confidence"
            ] = (
                value_region.confidence
            )

            entry[
                "value_box"
            ] = (
                value_region.box
            )

            entry[
                "evidence"
            ].append(
                value_region.text
            )

        if field not in result:

            result[
                field
            ] = entry

        else:

            existing = result[
                field
            ]

            if (
                existing.get(
                    "value"
                ) is None
                and value is not None
            ):

                result[
                    field
                ] = entry

            elif (
                value is not None
                and value != existing.get(
                    "value"
                )
            ):

                existing.setdefault(
                    "additional_values",
                    []
                ).append(
                    value
                )

    # --------------------------------------------------------
    # FSSAI LICENSE EXTRACTION
    # --------------------------------------------------------

    fssai_values = []

    seen = set()

    fssai_regions = [

        region

        for region in regions

        if "fssai"
        in clean_text(
            region.text
        )
    ]

    for region in regions:

        text = region.text

        lower = clean_text(
            text
        )

        has_fssai = (
            "fssai"
            in lower
        )

        has_license_label = bool(
            re.search(
                r"\blic(?:ence|ense)?"
                r"\s*\.?\s*no\b",
                lower,
                re.IGNORECASE
            )
        )

        if not (
            has_fssai
            or has_license_label
        ):

            continue

        # If this is only "Lic. No.", make sure it
        # is close to an FSSAI region.

        if (
            has_license_label
            and not has_fssai
        ):

            close = any(

                abs(
                    region.cy
                    -
                    f.cy
                ) <= 100

                and

                abs(
                    region.cx
                    -
                    f.cx
                ) <= 250

                for f in fssai_regions
            )

            if not close:
                continue

        numbers = extract_license_numbers(
            text
        )

        for number in numbers:

            if number in seen:
                continue

            seen.add(
                number
            )

            fssai_values.append(

                {
                    "value":
                        number,

                    "evidence": [
                        text
                    ],

                    "confidence":
                        region.confidence,

                    "box":
                        region.box
                }
            )

    if fssai_values:

        result[
            "fssai_license"
        ] = {

            "values": [
                item[
                    "value"
                ]
                for item in fssai_values
            ],

            "evidence":
                fssai_values
        }

    return result


def extract_license_numbers(
    text
):

    return re.findall(
        r"\b\d{8,20}\b",
        text
    )


# ============================================================
# SECTION EXTRACTION
# ============================================================

def extract_sections(
    regions,
    rows
):

    result = {}

    ordered = sorted(
        regions,
        key=lambda r: (
            r.row_id,
            r.x1
        )
    )

    for region in ordered:

        section = detect_section(
            region.text
        )

        # Nutrition is handled separately.

        if section == "nutrition":
            continue

        # Explicit allergen statement.

        if (
            section != "allergen"
            and looks_like_allergen_statement(
                region.text
            )
        ):

            section = "allergen"

        if section is None:
            continue

        content = []

        # ----------------------------------------------------
        # Inline content
        # ----------------------------------------------------

        aliases = SECTION_ALIASES[
            section
        ]

        normalized = normalize_text(
            region.text
        )

        for alias in sorted(
            aliases,
            key=len,
            reverse=True
        ):

            pattern = (
                r"^\s*"
                + re.escape(
                    normalize_text(
                        alias
                    )
                )
                + r"\s*[:\-]?\s*(.*)$"
            )

            match = re.match(
                pattern,
                normalized,
                re.IGNORECASE
            )

            if match:

                inline = match.group(
                    1
                ).strip()

                if inline:

                    content.append(
                        inline
                    )

                break

        # ----------------------------------------------------
        # Following rows
        # ----------------------------------------------------

        for row_id in range(
            region.row_id + 1,
            min(
                len(rows),
                region.row_id + 25
            )
        ):

            row = rows[
                row_id
            ]

            # Stop at another major section.

            if any(
                detect_section(
                    r.text
                )
                in {
                    "ingredients",
                    "nutrition",
                    "storage",
                    "allergen"
                }

                for r in row
            ):

                break

            # Stop at metadata.

            if any(
                detect_field(
                    r.text
                ) is not None

                for r in row
            ):

                break

            row.sort(
                key=lambda r: r.x1
            )

            row_content = []

            for item in row:

                # Keep text that is horizontally connected
                # to the current block.

                horizontal_distance = abs(
                    item.cx
                    -
                    region.cx
                )

                overlap = min(
                    region.x2,
                    item.x2
                ) - max(
                    region.x1,
                    item.x1
                )

                if (
                    horizontal_distance
                    <= max(
                        450,
                        region.width * 1.2
                    )
                    or overlap >= -25
                ):

                    row_content.append(
                        item.text
                    )

            if row_content:

                content.extend(
                    row_content
                )

        cleaned = []

        for item in content:

            item = normalize_text(
                item
            )

            if (
                item
                and item not in cleaned
            ):

                cleaned.append(
                    item
                )

        if cleaned:

            result[
                section
            ] = {

                "heading":
                    region.text,

                "content":
                    cleaned,

                "confidence":
                    region.confidence,

                "box":
                    region.box
            }

    # Explicit allergen fallback.

    if "allergen" not in result:

        for region in regions:

            if looks_like_allergen_statement(
                region.text
            ):

                result[
                    "allergen"
                ] = {

                    "heading":
                        "ALLERGEN STATEMENT",

                    "content": [
                        region.text
                    ],

                    "confidence":
                        region.confidence,

                    "box":
                        region.box
                }

                break

    return result


# ============================================================
# NUTRITION FUNCTIONS
# ============================================================

def detect_nutrient(
    text
):

    compact = compact_text(
        text
    )

    matches = []

    for alias, canonical in (
        NUTRIENT_ALIASES
    ):

        alias_compact = compact_text(
            alias
        )

        if (
            compact == alias_compact
            or compact.startswith(
                alias_compact
            )
        ):

            matches.append(
                (
                    len(
                        alias_compact
                    ),
                    canonical
                )
            )

    if not matches:
        return None

    return max(
        matches,
        key=lambda x: x[0]
    )[1]


def is_numeric_cell(
    text
):

    return bool(
        re.fullmatch(
            r"\s*"
            r"(?:[-<]\s*)?"
            r"\d+(?:\.\d+)?"
            r"(?:\s*(?:mg|g|kg|ml|kcal|kj|%))?"
            r"\s*",
            text,
            re.IGNORECASE
        )
    )


def extract_number(
    text
):

    match = re.search(
        r"\d+(?:\.\d+)?",
        text
    )

    return (
        match.group(0)
        if match
        else None
    )


def find_nutrition_heads(
    rows
):

    headings = []

    for row_id, row in enumerate(
        rows
    ):

        for region in row:

            if detect_section(
                region.text
            ) == "nutrition":

                headings.append(
                    (
                        row_id,
                        region
                    )
                )

    return headings


def find_nutrition_block(
    rows,
    start_row
):

    end_row = len(rows)

    # Search until another major section
    # starts or a big visual gap occurs.

    previous_y = None

    for row_id in range(
        start_row + 1,
        len(rows)
    ):

        row = rows[
            row_id
        ]

        if not row:
            continue

        current_y = statistics.mean(
            [
                r.cy
                for r in row
            ]
        )

        if previous_y is not None:

            gap = (
                current_y
                -
                previous_y
            )

            if gap > 100:

                end_row = row_id

                break

        previous_y = current_y

        if any(
            detect_section(
                r.text
            )
            in {
                "ingredients",
                "storage",
                "allergen"
            }
            for r in row
        ):

            end_row = row_id

            break

    return rows[
        start_row:end_row
    ]


def detect_column_anchors(
    block_rows
):

    anchors = {}

    # Only inspect the first ~8 rows.
    header_rows = block_rows[
        :8
    ]

    for row in header_rows:

        for region in row:

            c = compact_text(
                region.text
            )

            # ----------------------------------------------
            # Per 100 g
            # ----------------------------------------------

            if (
                "per100g" in c
                or "per100" in c
            ):

                anchors[
                    "per_100g"
                ] = region.cx

            # ----------------------------------------------
            # Per serving
            # ----------------------------------------------

            elif (
                "perserve" in c
                or "perserving" in c
                or "amountperserving" in c
            ):

                anchors[
                    "per_serving"
                ] = region.cx

            # ----------------------------------------------
            # RDA / Daily value
            # ----------------------------------------------

            elif (
                "rda" in c
                or "rdaperserve" in c
                or "%rda" in c
                or "dailyvalue" in c
                or "%dailyvalue" in c
            ):

                anchors[
                    "percent_rda"
                ] = region.cx

    # --------------------------------------------------------
    # Important:
    #
    # If a "per serve" header is actually the same column
    # as "%RDA" due to OCR splitting, remove the duplicate.
    # --------------------------------------------------------

    if (
        "per_serving" in anchors
        and "percent_rda" in anchors
    ):

        if abs(
            anchors[
                "per_serving"
            ]
            -
            anchors[
                "percent_rda"
            ]
        ) < 28:

            # Keep the actual RDA column.
            anchors.pop(
                "per_serving"
            )

    return anchors


def nutrition_row_cells(
    row,
    nutrient_region
):

    cells = []

    for region in row:

        if (
            region.index
            ==
            nutrient_region.index
        ):

            continue

        # Nutrient label is generally on the left.
        if region.x1 < (
            nutrient_region.x2
            -
            5
        ):

            continue

        if is_numeric_cell(
            region.text
        ):

            cells.append(
                region
            )

    cells.sort(
        key=lambda r: r.cx
    )

    return cells


def assign_cells_to_columns(
    cells,
    anchors
):

    if not cells:
        return {}

    if not anchors:

        result = {}

        if len(cells) >= 1:

            result[
                "value"
            ] = cells[0]

        if len(cells) >= 2:

            result[
                "percent_rda"
            ] = cells[-1]

        return result

    assignments = {}

    unused = list(
        cells
    )

    # --------------------------------------------------------
    # Each cell can be assigned to only one column.
    # --------------------------------------------------------

    for column, x in sorted(
        anchors.items(),
        key=lambda item: item[1]
    ):

        if not unused:
            break

        candidate = min(
            unused,
            key=lambda r: abs(
                r.cx - x
            )
        )

        distance = abs(
            candidate.cx
            -
            x
        )

        if distance <= 65:

            assignments[
                column
            ] = candidate

            unused.remove(
                candidate
            )

    return assignments


def reconstruct_nutrition_table(
    block_rows,
    heading
):

    anchors = detect_column_anchors(
        block_rows
    )

    rows_result = {}

    for row in block_rows:

        nutrient_regions = [

            region

            for region in row

            if detect_nutrient(
                region.text
            ) is not None
        ]

        if not nutrient_regions:
            continue

        # Use the left-most nutrient label.

        nutrient_region = min(
            nutrient_regions,
            key=lambda r: r.x1
        )

        nutrient = detect_nutrient(
            nutrient_region.text
        )

        if nutrient is None:
            continue

        cells = nutrition_row_cells(
            row,
            nutrient_region
        )

        if not cells:
            continue

        assignments = (
            assign_cells_to_columns(
                cells,
                anchors
            )
        )

        if not assignments:
            continue

        row_data = {

            "evidence_label":
                nutrient_region.text,

            "confidence":
                nutrient_region.confidence,

            "box":
                nutrient_region.box
        }

        # Store column values exactly as OCR read them.

        for column, cell in assignments.items():

            row_data[
                column
            ] = cell.text

            row_data[
                column + "_evidence"
            ] = {

                "text":
                    cell.text,

                "confidence":
                    cell.confidence,

                "box":
                    cell.box
            }

        rows_result[
            nutrient
        ] = row_data

    return {

        "heading":
            heading.text,

        "heading_confidence":
            heading.confidence,

        "heading_box":
            heading.box,

        "columns":
            anchors,

        "rows":
            rows_result
    }


def extract_nutrition_tables(
    rows
):

    headings = find_nutrition_heads(
        rows
    )

    tables = []

    for index, (
        row_id,
        heading
    ) in enumerate(headings):

        block = find_nutrition_block(
            rows,
            row_id
        )

        table = reconstruct_nutrition_table(
            block,
            heading
        )

        if table[
            "rows"
        ]:

            tables.append(
                table
            )

    return tables


# ============================================================
# CONTACT INFORMATION
# ============================================================

def extract_contacts(
    regions
):

    phones = []
    emails = []
    websites = []

    for region in regions:

        text = region.text

        # Mobile numbers.

        for value in re.findall(
            r"(?<!\d)"
            r"[6-9]\d{9}"
            r"(?!\d)",
            text
        ):

            if value not in phones:

                phones.append(
                    value
                )

        # Indian landline.

        for value in re.findall(
            r"\+91[\s-]?"
            r"\d{2,5}[\s-]"
            r"\d{5,8}",
            text
        ):

            if value not in phones:

                phones.append(
                    value
                )

        for value in extract_email(
            text
        ):

            if value not in emails:

                emails.append(
                    value
                )

        for value in extract_website(
            text
        ):

            if value not in websites:

                websites.append(
                    value
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
# COMPLETE ARRANGER
# ============================================================

def arrange(
    ocr_data
):

    regions = make_regions(
        ocr_data
    )

    rows = build_rows(
        regions
    )

    metadata = extract_metadata(
        regions,
        rows
    )

    sections = extract_sections(
        regions,
        rows
    )

    nutrition_tables = (
        extract_nutrition_tables(
            rows
        )
    )

    contacts = extract_contacts(
        regions
    )

    return {

        "success":
            True,

        "source_image":
            ocr_data.get(
                "image"
            ),

        "product_information":
            metadata,

        "sections":
            sections,

        "nutrition_tables":
            nutrition_tables,

        "contacts":
            contacts,

        "layout": {

            "ocr_regions":
                len(regions),

            "visual_rows":
                len(rows)
        },

        # Original OCR is preserved.
        "raw_ocr":
            ocr_data.get(
                "regions",
                []
            )
    }


# ============================================================
# OCR READER
# ============================================================

class ProductReader:

    def __init__(
        self
    ):

        print(
            "=" * 70
        )

        print(
            "INITIALIZING GENERAL FOOD LABEL READER V6"
        )

        print(
            "=" * 70
        )

        print()

        try:

            self.ocr = PaddleOCR(

                lang="en",

                use_doc_orientation_classify=False,

                use_doc_unwarping=False,

                use_textline_orientation=False,

                enable_mkldnn=False
            )

        except Exception as exc:

            print(
                "ERROR: Could not initialize PaddleOCR."
            )

            print(
                str(exc)
            )

            sys.exit(1)

        print(
            "OCR model loaded successfully."
        )

        print()

    def read_ocr(
        self,
        image_path
    ):

        if not os.path.isfile(
            image_path
        ):

            raise FileNotFoundError(
                image_path
            )

        print(
            "=" * 70
        )

        print(
            "READING IMAGE"
        )

        print(
            "=" * 70
        )

        print(
            "Image:",
            image_path
        )

        print()

        results = self.ocr.predict(
            image_path
        )

        regions = []

        for result in results:

            try:

                data = result[
                    "res"
                ]

            except Exception:

                data = result

            texts = data.get(
                "rec_texts",
                []
            )

            scores = data.get(
                "rec_scores",
                []
            )

            boxes = data.get(
                "rec_boxes",
                []
            )

            for i, text in enumerate(
                texts
            ):

                text = normalize_text(
                    text
                )

                if not text:
                    continue

                confidence = None

                if i < len(
                    scores
                ):

                    confidence = safe_float(
                        scores[i]
                    )

                box = None

                if i < len(
                    boxes
                ):

                    raw_box = boxes[
                        i
                    ]

                    if hasattr(
                        raw_box,
                        "tolist"
                    ):

                        box = (
                            raw_box.tolist()
                        )

                    else:

                        box = raw_box

                regions.append(

                    {

                        "text":
                            text,

                        "confidence":
                            confidence,

                        "box":
                            box
                    }
                )

        return {

            "success":
                True,

            "image":
                os.path.abspath(
                    image_path
                ),

            "regions":
                regions,

            "full_text":
                "\n".join(

                    region[
                        "text"
                    ]

                    for region
                    in regions
                )
        }


# ============================================================
# IMAGE SELECTOR
# ============================================================

def select_image():

    root = Tk()

    root.withdraw()

    root.attributes(
        "-topmost",
        True
    )

    path = filedialog.askopenfilename(

        title=
            "Select Product Image",

        filetypes=[

            (
                "Image files",
                "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"
            ),

            (
                "All files",
                "*.*"
            )
        ]
    )

    root.destroy()

    return path


# ============================================================
# RESULT DISPLAY
# ============================================================

def display_result(
    result
):

    print()

    print(
        "=" * 70
    )

    print(
        "STRUCTURED PRODUCT INFORMATION"
    )

    print(
        "=" * 70
    )

    fields = result[
        "product_information"
    ]

    if not fields:

        print(
            "No metadata fields detected."
        )

    for name, data in fields.items():

        if name == "fssai_license":

            print(

                f"{name:25} : "
                f"{data.get('values', [])}"

            )

            continue

        print(

            f"{name:25} : "
            f"{data.get('value')}"

        )

        if data.get(
            "additional_values"
        ):

            print(

                " " * 27
                + "Additional: "
                + str(
                    data[
                        "additional_values"
                    ]
                )

            )

    print()

    print(
        "=" * 70
    )

    print(
        "SECTIONS"
    )

    print(
        "=" * 70
    )

    sections = result[
        "sections"
    ]

    if not sections:

        print(
            "No sections detected."
        )

    for name, data in sections.items():

        print()

        print(
            f"[{name.upper()}]"
        )

        for line in data[
            "content"
        ]:

            print(
                "  "
                + line
            )

    print()

    print(
        "=" * 70
    )

    print(
        "NUTRITION TABLES"
    )

    print(
        "=" * 70
    )

    tables = result[
        "nutrition_tables"
    ]

    if not tables:

        print(
            "No nutrition tables detected."
        )

    for table_number, table in enumerate(
        tables,
        start=1
    ):

        print()

        print(
            f"TABLE {table_number}"
        )

        print(
            table[
                "heading"
            ]
        )

        for nutrient, row in table[
            "rows"
        ].items():

            values = []

            for key in (
                "value",
                "per_100g",
                "per_serving",
                "percent_rda",
                "percent_daily_value"
            ):

                if key in row:

                    values.append(

                        f"{key}="
                        f"{row[key]}"

                    )

            print(

                f"{nutrient:25} : "
                + " | ".join(values)

            )

    print()

    print(
        "=" * 70
    )

    print(
        "CONTACT INFORMATION"
    )

    print(
        "=" * 70
    )

    contacts = result[
        "contacts"
    ]

    print(
        "Phones   :",
        contacts[
            "phones"
        ]
    )

    print(
        "Emails   :",
        contacts[
            "emails"
        ]
    )

    print(
        "Websites :",
        contacts[
            "websites"
        ]
    )

    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print(
        "=" * 70
    )

    print(
        "GENERAL FOOD LABEL READER V6"
    )

    print(
        "OCR + EFFICIENT SPATIAL ARRANGER"
    )

    print(
        "=" * 70
    )

    print()

    image_path = select_image()

    if not image_path:

        print(
            "No image selected."
        )

        return

    reader = ProductReader()

    try:

        # ----------------------------------------------------
        # OCR
        # ----------------------------------------------------

        ocr_result = reader.read_ocr(
            image_path
        )

        # ----------------------------------------------------
        # OUTPUT DIRECTORY
        # ----------------------------------------------------

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

        raw_file = os.path.join(
            output_dir,
            "ocr_result.json"
        )

        result_file = os.path.join(
            output_dir,
            "product_result.json"
        )

        # ----------------------------------------------------
        # SAVE RAW OCR
        # ----------------------------------------------------

        with open(
            raw_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                ocr_result,
                file,
                indent=2,
                ensure_ascii=False
            )

        print()

        print(
            "OCR regions:",
            len(
                ocr_result[
                    "regions"
                ]
            )
        )

        print()

        print(
            "Arranging information..."
        )

        # ----------------------------------------------------
        # ARRANGE
        # ----------------------------------------------------

        result = arrange(
            ocr_result
        )

        # ----------------------------------------------------
        # SAVE FINAL RESULT
        # ----------------------------------------------------

        with open(
            result_file,
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
            "=" * 70
        )

        print(
            "COMPLETE"
        )

        print(
            "=" * 70
        )

        print(
            "Raw OCR     :",
            raw_file
        )

        print(
            "Final result:",
            result_file
        )

        print(
            "OCR regions :",
            result[
                "layout"
            ][
                "ocr_regions"
            ]
        )

        print(
            "Visual rows :",
            result[
                "layout"
            ][
                "visual_rows"
            ]
        )

        display_result(
            result
        )

    except Exception as exc:

        print()

        print(
            "=" * 70
        )

        print(
            "READER FAILED"
        )

        print(
            "=" * 70
        )

        print(
            str(exc)
        )

        print()

        raise


if __name__ == "__main__":

    main()