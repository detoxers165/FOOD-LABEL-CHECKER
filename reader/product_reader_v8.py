# ============================================================
# GENERAL FOOD LABEL READER - V5
# ============================================================
#
# IMAGE
#   ↓
# PADDLEOCR
#   ↓
# RAW OCR + BOXES
#   ↓
# VISUAL ROWS
#   ↓
# LOCAL FIELD MATCHING
#   ↓
# NUTRITION TABLE RECONSTRUCTION
#   ↓
# STRUCTURED RESULT
#
# Generic: no brand/product-specific coordinates or assumptions.
# ============================================================

import json
import os
import re
import sys
import statistics
from dataclasses import dataclass
from tkinter import Tk, filedialog


# ============================================================
# PADDLE SAFE SETTINGS
# ============================================================

os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")

try:
    from paddleocr import PaddleOCR
except Exception as exc:
    print("ERROR: Could not import PaddleOCR.")
    print(str(exc))
    sys.exit(1)


# ============================================================
# GENERIC METADATA ALIASES
# ============================================================

FIELD_ALIASES = {
    "net_quantity": [
        "net quantity",
        "net qty",
        "net weight",
        "net wt",
        "net content",
        "net contents",
    ],

    "mrp": [
        "maximum retail price",
        "max retail price",
        "maximum retail selling price",
        "mrp",
    ],

    "batch_number": [
        "batch number",
        "batch no",
        "batch no.",
        "batch code",
        "lot number",
        "lot no",
        "lot no.",
        "lot code",
    ],

    "manufacturing_date": [
        "date of manufacture",
        "manufacturing date",
        "manufactured date",
        "mfg date",
        "mfg. date",
        "date of mfg",
        "packed on",
        "packing date",
    ],

    "expiry_date": [
        "expiry date",
        "expiration date",
        "exp date",
        "exp. date",
        "use by",
        "use before",
        "best before",
    ],

    "manufacturer": [
        "manufactured by",
        "manufactured for",
        "manufacturer",
        "mfd by",
        "mfd. by",
    ],

    "marketed_by": [
        "marketed by",
        "marketed for",
    ],

    "customer_care": [
        "customer care",
        "consumer care",
        "customer service",
        "consumer service",
        "contact us",
        "helpline",
        "help line",
    ],

    "email": [
        "email",
        "e-mail",
    ],

    "website": [
        "website",
        "web site",
    ],
}


# ============================================================
# SECTION ALIASES
# ============================================================

SECTION_ALIASES = {
    "ingredients": [
        "ingredients",
        "ingredient",
    ],

    "nutrition": [
        "nutrition information",
        "nutritional information",
        "nutrition facts",
        "nutrition",
    ],

    "storage": [
        "storage instructions",
        "storage conditions",
        "storage",
    ],
}


# Common allergen words are used ONLY to identify an
# allergen statement, not to make a compliance judgment.
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
    "sulfites",
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
    ("fiber", "fiber"),
]


# ============================================================
# DATA MODEL
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
        "”": '"',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"\s+", " ", text).strip()


def compact_text(text):
    """
    Used for matching OCR variants such as:
    -AddedSugars(g)
    -Saturatedfat(g)
    - Total Sugars(g)
    """
    text = normalize_text(text).lower()

    # Remove leading bullets/dashes/quotes.
    text = re.sub(
        r"^[\s\-\*•·\"']+",
        "",
        text
    )

    return re.sub(
        r"[^a-z0-9%₹]",
        "",
        text
    )


def clean_match_text(text):
    text = normalize_text(text).lower()

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


# ============================================================
# BOX PARSING
# ============================================================

def parse_box(box):
    """
    Supports PaddleOCR rec_boxes:

        [x1, y1, x2, y2]

    and polygons:

        [[x1,y1], [x2,y2], ...]
    """

    if box is None:
        return None

    try:

        if (
            isinstance(box, (list, tuple))
            and len(box) == 4
            and all(
                isinstance(v, (int, float))
                for v in box
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
                max(y1, y2),
            )

        xs = []
        ys = []

        for point in box:

            if (
                isinstance(point, (list, tuple))
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
                max(ys),
            )

    except Exception:
        return None

    return None


def make_regions(ocr_data):
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
            raw.get("box")
        )

        if not text or bounds is None:
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
                ),
            )
        )

    return regions


# ============================================================
# VISUAL ROW DETECTION
# ============================================================

def build_rows(regions):
    """
    Groups OCR regions into visual rows.

    This is intentionally local: it does not globally merge
    unrelated parts of the package.
    """

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
        [r.height for r in regions]
    )

    tolerance = max(
        5.0,
        min(
            10.0,
            median_height * 0.55
        )
    )

    rows = []
    centers = []

    for region in ordered:

        best_index = None
        best_difference = float(
            "inf"
        )

        for i, center in enumerate(
            centers
        ):

            difference = abs(
                region.cy - center
            )

            if (
                difference <= tolerance
                and difference < best_difference
            ):

                best_index = i
                best_difference = (
                    difference
                )

        if best_index is None:

            rows.append(
                [region]
            )

            centers.append(
                region.cy
            )

        else:

            rows[
                best_index
            ].append(region)

            centers[
                best_index
            ] = sum(
                r.cy
                for r in rows[
                    best_index
                ]
            ) / len(
                rows[
                    best_index
                ]
            )

    pairs = sorted(
        zip(
            centers,
            rows
        ),
        key=lambda item: item[0]
    )

    final_rows = []

    for row_id, (_, row) in enumerate(
        pairs
    ):

        row.sort(
            key=lambda r: r.x1
        )

        for region in row:
            region.row_id = row_id

        final_rows.append(
            row
        )

    return final_rows


# ============================================================
# GENERIC LABEL DETECTION
# ============================================================

def alias_at_start(
    text,
    aliases
):

    normalized = clean_match_text(
        text
    )

    compact = compact_text(
        text
    )

    candidates = []

    for alias in aliases:

        a_text = clean_match_text(
            alias
        )

        a_compact = compact_text(
            alias
        )

        if (
            normalized == a_text
            or normalized.startswith(
                a_text + " "
            )
            or normalized.startswith(
                a_text + ":"
            )
            or normalized.startswith(
                a_text + "-"
            )
            or compact == a_compact
            or compact.startswith(
                a_compact
            )
        ):

            candidates.append(
                (
                    len(a_compact),
                    alias
                )
            )

    if not candidates:
        return False

    return max(
        candidates
    )


def detect_field(text):

    hits = []

    for field, aliases in (
        FIELD_ALIASES.items()
    ):

        hit = alias_at_start(
            text,
            aliases
        )

        if hit:

            hits.append(
                (
                    hit[0],
                    field
                )
            )

    if not hits:
        return None

    return max(
        hits,
        key=lambda item: item[0]
    )[1]


def detect_section(text):

    for section, aliases in (
        SECTION_ALIASES.items()
    ):

        if alias_at_start(
            text,
            aliases
        ):

            return section

    # OCR may merge "NUTRITIONALINFORMATION".
    compact = compact_text(
        text
    )

    if compact.startswith(
        "nutritionalinformation"
    ):

        return "nutrition"

    if compact.startswith(
        "nutritionfacts"
    ):

        return "nutrition"

    return None


def detect_allergen_statement(
    text
):

    normalized = clean_match_text(
        text
    )

    starts_like = (
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
            "allergen "
        )
    )

    if not starts_like:
        return False

    compact = compact_text(
        text
    )

    return any(
        word in compact
        for word in (
            compact_text(
                allergen
            )
            for allergen in ALLERGEN_WORDS
        )
    )


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
    r"\d{2,4}\b",
]


def extract_date(text):

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


def extract_weight(text):

    match = re.search(
        r"\b\d+(?:\.\d+)?\s*"
        r"(?:mg|g|kg|ml|l|litre|liter|cl)\b",
        text,
        re.IGNORECASE
    )

    return (
        match.group(
            0
        )
        if match
        else None
    )


def extract_price(text):

    normalized = normalize_text(
        text
    )

    # Reject cost-per-unit / USP style strings.
    if re.search(
        r"\b(?:usp|per|/)\b",
        normalized,
        re.IGNORECASE
    ):
        # A genuine MRP region can still contain
        # "MRP ₹10 inclusive..." so only reject
        # when the whole candidate is clearly a
        # unit-rate expression.
        if re.search(
            r"(?:usp|/\s*[a-zA-Z]+|per\s+[a-zA-Z]+)",
            normalized,
            re.IGNORECASE
        ):
            return None

    # Currency-prefixed price.
    match = re.search(
        r"(?:₹|rs\.?|inr)\s*"
        r"\d+(?:,\d{3})*"
        r"(?:\.\d{1,2})?",
        normalized,
        re.IGNORECASE
    )

    if match:
        return match.group(
            0
        ).strip()

    # A pure numeric region is also allowed.
    if re.fullmatch(
        r"\s*\d+(?:\.\d{1,2})?\s*",
        normalized
    ):

        return normalized.strip()

    return None


def extract_license_numbers(
    text
):

    return re.findall(
        r"\b\d{8,20}\b",
        text
    )


def extract_batch(text):

    value = normalize_text(
        text
    ).strip(
        " .:-"
    )

    if not value:
        return None

    if len(value) > 30:
        return None

    # Avoid ordinary sentences.
    if len(value.split()) > 2:
        return None

    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._/-]{3,25}",
        value
    ):
        return None

    # A useful batch code normally contains a digit.
    if not any(
        ch.isdigit()
        for ch in value
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

    found = re.findall(
        r"(?:https?://|www\.)"
        r"[^\s,;]+",
        text,
        re.IGNORECASE
    )

    return [
        value.rstrip(
            ".,;)"
        )
        for value in found
    ]


# ============================================================
# INLINE LABEL VALUE
# ============================================================

def inline_value(
    field,
    text
):

    aliases = FIELD_ALIASES[
        field
    ]

    normalized = normalize_text(
        text
    )

    for alias in sorted(
        aliases,
        key=len,
        reverse=True
    ):

        alias_norm = normalize_text(
            alias
        )

        pattern = (
            r"^\s*"
            + re.escape(
                alias_norm
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

        if field == "email":

            emails = extract_email(
                rest
            )

            return (
                emails[0]
                if emails
                else None
            )

        if field == "website":

            sites = extract_website(
                rest
            )

            return (
                sites[0]
                if sites
                else None
            )

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

        return (
            rest
            if re.search(
                r"[A-Za-z0-9]",
                rest
            )
            else None
        )

    return None


# ============================================================
# FIELD-SPECIFIC VALIDATION
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

    if field == "fssai_license":
        return bool(
            extract_license_numbers(
                text
            )
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

    return bool(
        re.search(
            r"[A-Za-z0-9]",
            text
        )
    )


# ============================================================
# LOCAL SPATIAL MATCH
# ============================================================

def same_row_score(
    label,
    candidate,
    field
):

    vertical_gap = abs(
        candidate.cy
        - label.cy
    )

    row_tolerance = max(
        label.height,
        candidate.height,
        8.0
    ) * 1.35

    if vertical_gap > row_tolerance:
        return -1

    if (
        candidate.x1 >= label.x2
    ):

        gap = candidate.x1 - label.x2

        if gap > max(
            280,
            label.width * 5
        ):
            return -1

        direction_bonus = 1000
        horizontal_penalty = (
            gap * 1.2
        )

    else:

        gap = label.x1 - candidate.x2

        if gap > 180:
            return -1

        direction_bonus = 350
        horizontal_penalty = (
            gap * 1.8
        )

    if not valid_field_value(
        field,
        candidate.text
    ):
        return -1

    return (
        direction_bonus
        - horizontal_penalty
        - vertical_gap * 5
    )


def below_score(
    label,
    candidate,
    field
):

    vertical_gap = (
        candidate.y1
        - label.y2
    )

    if vertical_gap < -5:
        return -1

    if vertical_gap > 180:
        return -1

    horizontal_gap = abs(
        candidate.cx
        - label.cx
    )

    if horizontal_gap > max(
        220,
        label.width * 4
    ):
        return -1

    if not valid_field_value(
        field,
        candidate.text
    ):
        return -1

    return (
        650
        - vertical_gap * 2
        - horizontal_gap * 1.1
    )


def find_field_value(
    label,
    field,
    rows,
    used
):

    candidates = []

    if 0 <= label.row_id < len(
        rows
    ):

        for candidate in rows[
            label.row_id
        ]:

            if candidate.index == label.index:
                continue

            if candidate.index in used:
                continue

            if detect_field(
                candidate.text
            ) is not None:
                continue

            score = same_row_score(
                label,
                candidate,
                field
            )

            if score > 0:
                candidates.append(
                    (
                        score,
                        candidate
                    )
                )

    if candidates:

        candidates.sort(
            key=lambda x: x[0],
            reverse=True
        )

        return candidates[0]

    # Only a few rows below.
    start = label.row_id + 1
    end = min(
        len(rows),
        start + 4
    )

    for row_id in range(
        start,
        end
    ):

        row_candidates = []

        for candidate in rows[
            row_id
        ]:

            if candidate.index in used:
                continue

            if detect_field(
                candidate.text
            ) is not None:
                continue

            score = below_score(
                label,
                candidate,
                field
            )

            if score > 0:
                row_candidates.append(
                    (
                        score,
                        candidate
                    )
                )

        if row_candidates:

            row_candidates.sort(
                key=lambda x: x[0],
                reverse=True
            )

            return row_candidates[0]

    return None


# ============================================================
# FIELD EXTRACTION
# ============================================================

def extract_product_fields(
    regions,
    rows
):

    fields = {}
    used = set()

    for region in regions:

        field = detect_field(
            region.text
        )

        if field is None:
            continue

        # FSSAI is handled separately.
        if field == "fssai_license":
            continue

        value = inline_value(
            field,
            region.text
        )

        value_region = None

        if value is not None:
            value_region = region

        else:

            match = find_field_value(
                region,
                field,
                rows,
                used
            )

            if match:

                _, candidate = match

                value = inline_value(
                    field,
                    candidate.text
                )

                if value is None:
                    if valid_field_value(
                        field,
                        candidate.text
                    ):
                        value = candidate.text

                if value is not None:
                    value_region = candidate
                    used.add(
                        candidate.index
                    )

        entry = {
            "value": value,
            "label": region.text,
            "label_confidence": region.confidence,
            "label_box": region.box,
            "evidence": [
                region.text
            ],
        }

        if (
            value_region is not None
            and value_region.index != region.index
        ):

            entry[
                "value_confidence"
            ] = value_region.confidence

            entry[
                "value_box"
            ] = value_region.box

            entry[
                "evidence"
            ].append(
                value_region.text
            )

        if field not in fields:

            fields[
                field
            ] = entry

        else:

            existing = fields[
                field
            ]

            if (
                existing.get(
                    "value"
                ) is None
                and value is not None
            ):

                fields[
                    field
                ] = entry

            elif (
                value is not None
                and value
                != existing.get(
                    "value"
                )
            ):

                existing.setdefault(
                    "additional_values",
                    []
                )

                values = (
                    value
                    if isinstance(
                        value,
                        list
                    )
                    else [value]
                )

                for item in values:

                    if item not in existing[
                        "additional_values"
                    ]:

                        existing[
                            "additional_values"
                        ].append(
                            item
                        )

                        existing[
                            "evidence"
                        ].extend(
                            entry[
                                "evidence"
                            ]
                        )

    return fields


# ============================================================
# FSSAI EXTRACTION
# ============================================================

def extract_fssai(
    regions
):

    results = []
    seen = set()

    # The FSSAI logo/word and the licence number can be
    # separate OCR regions. A plain "Lic. No." is accepted
    # only when it is spatially close to an FSSAI region.
    fssai_regions = [
        r for r in regions
        if "fssai" in clean_match_text(r.text)
    ]

    for region in regions:

        text = region.text
        lower = clean_match_text(text)

        has_fssai_word = (
            "fssai" in lower
        )

        has_license_label = bool(
            re.search(
                r"\blic(?:ence|ense)?\s*\.?\s*no\b",
                lower,
                re.IGNORECASE
            )
        )

        if has_license_label and not has_fssai_word:

            if not fssai_regions:
                continue

            close_to_fssai = any(
                abs(region.cy - f.cy) <= 120
                and abs(region.cx - f.cx) <= 220
                for f in fssai_regions
            )

            if not close_to_fssai:
                continue

        if not (
            has_fssai_word
            or has_license_label
        ):
            continue

        numbers = extract_license_numbers(
            text
        )

        for number in numbers:

            if number in seen:
                continue

            results.append(
                {
                    "value": number,
                    "evidence": [text],
                    "confidence": region.confidence,
                    "box": region.box,
                }
            )

            seen.add(
                number
            )

    return results


# ============================================================
# SECTION EXTRACTION
# ============================================================

def section_inline(
    text,
    section
):

    aliases = SECTION_ALIASES[
        section
    ]

    normalized = normalize_text(
        text
    )

    for alias in sorted(
        aliases,
        key=len,
        reverse=True
    ):

        pattern = (
            r"^\s*"
            + re.escape(
                normalize_text(alias)
            )
            + r"\s*[:\-]?\s*(.*)$"
        )

        match = re.match(
            pattern,
            normalized,
            re.IGNORECASE
        )

        if match:

            rest = match.group(
                1
            ).strip()

            if rest:
                return rest

    # Special merged form:
    # NUTRITIONALINFORMATION...
    if section == "nutrition":

        merged = re.match(
            r"^\s*NUTRITIONAL"
            r"INFORMATION"
            r"\s*(.*)$",
            normalized,
            re.IGNORECASE
        )

        if merged:

            rest = merged.group(
                1
            ).strip()

            return rest or None

    return None


def is_stop_region(
    region
):

    if detect_section(
        region.text
    ) is not None:
        return True

    if detect_allergen_statement(
        region.text
    ):
        return True

    if detect_field(
        region.text
    ) is not None:
        return True

    return False


def extract_sections(
    regions,
    rows
):

    sections = {}

    for region in regions:

        section = detect_section(
            region.text
        )

        if section is None:
            continue

        # Nutrition is handled as a table.
        if section == "nutrition":
            continue

        content = []

        inline = section_inline(
            region.text,
            section
        )

        if inline:
            content.append(
                inline
            )

        # Walk subsequent visual rows.
        for row_id in range(
            region.row_id + 1,
            min(
                len(rows),
                region.row_id + 20
            )
        ):

            row = rows[
                row_id
            ]

            if any(
                is_stop_region(
                    item
                )
                for item in row
            ):
                break

            row.sort(
                key=lambda x: x.x1
            )

            for item in row:

                # Keep text belonging to the same
                # local label block.
                overlap = min(
                    region.x2,
                    item.x2
                ) - max(
                    region.x1,
                    item.x1
                )

                near = abs(
                    item.cx
                    - region.cx
                ) <= max(
                    150,
                    region.width * 0.8
                )

                if (
                    overlap >= -25
                    or near
                ):

                    content.append(
                        item.text
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

            sections[
                section
            ] = {
                "heading": (
                    "INGREDIENTS"
                    if section == "ingredients"
                    else section.upper()
                ),
                "content": cleaned,
                "confidence": region.confidence,
                "box": region.box,
            }

    # Allergen statements are deliberately separate from
    # generic "contains" text.
    for region in regions:

        if not detect_allergen_statement(
            region.text
        ):
            continue

        sections[
            "allergen"
        ] = {
            "heading": "ALLERGEN STATEMENT",
            "content": [
                region.text
            ],
            "confidence": region.confidence,
            "box": region.box,
        }

        break

    return sections


# ============================================================
# NUTRITION TABLE DETECTION
# ============================================================

def numeric_token(
    text
):

    return re.fullmatch(
        r"\s*"
        r"\d+(?:\.\d+)?"
        r"\s*"
        r"(?:%|mg|g|kg|ml|kcal|kj)?"
        r"\s*",
        text,
        re.IGNORECASE
    ) is not None


def extract_number(
    text
):

    match = re.search(
        r"\d+(?:\.\d+)?",
        text
    )

    return (
        match.group(
            0
        )
        if match
        else None
    )


def nutrient_unit(
    text
):

    lower = text.lower()

    if "kcal" in lower:
        return "kcal"

    if re.search(
        r"\bmg\b",
        lower
    ):
        return "mg"

    if re.search(
        r"\bg\b",
        lower
    ):
        return "g"

    if re.search(
        r"\bkj\b",
        lower
    ):
        return "kJ"

    if re.search(
        r"\bml\b",
        lower
    ):
        return "mL"

    if re.search(
        r"\bkg\b",
        lower
    ):
        return "kg"

    return None


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
                    len(alias_compact),
                    canonical
                )
            )

    if not matches:
        return None

    return max(
        matches,
        key=lambda x: x[0]
    )[1]


def detect_nutrition_heading_rows(
    regions
):

    rows = set()

    for region in regions:

        if detect_section(
            region.text
        ) == "nutrition":

            rows.add(
                region.row_id
            )

    return rows


def detect_table_columns(
    rows,
    nutrition_heading_rows
):

    # Search the first few rows after the nutrition heading.
    candidate_rows = []

    if nutrition_heading_rows:

        first_heading = min(
            nutrition_heading_rows
        )

        for row_id in range(
            first_heading + 1,
            min(
                len(rows),
                first_heading + 6
            )
        ):

            candidate_rows.append(
                rows[row_id]
            )

    anchors = {}

    for row in candidate_rows:

        for region in row:

            c = compact_text(
                region.text
            )

            if (
                "per100" in c
                or "per100g" in c
            ):

                anchors.setdefault(
                    "per_100g",
                    []
                ).append(
                    region.cx
                )

            elif (
                "perserve" in c
                or "perserving" in c
            ):

                anchors.setdefault(
                    "per_serving",
                    []
                ).append(
                    region.cx
                )

            elif (
                "rda" in c
                or "%rda" in c
            ):

                anchors.setdefault(
                    "percent_rda",
                    []
                ).append(
                    region.cx
                )

    # A lower "per serve" label can sit under the "%RDA"
    # header. Do not treat that as a second serving column.
    if "percent_rda" in anchors and "per_serving" in anchors:
        rda_x = sum(anchors["percent_rda"]) / len(anchors["percent_rda"])

        anchors["per_serving"] = [
            x for x in anchors["per_serving"]
            if abs(x - rda_x) > 25
        ]

        if not anchors["per_serving"]:
            anchors.pop("per_serving")

    # Normalize each anchor to mean x.
    for key, values in list(
        anchors.items()
    ):

        if not values:
            anchors.pop(key)
            continue

        anchors[key] = sum(
            values
        ) / len(
            values
        )

    return anchors


def choose_numeric_cells(
    row,
    nutrient_region,
    anchors
):

    cells = []

    for region in row:

        if region.index == nutrient_region.index:
            continue

        if not numeric_token(
            region.text
        ):
            continue

        cells.append(
            region
        )

    cells.sort(
        key=lambda r: r.cx
    )

    if not cells:
        return {}

    # If column anchors exist, map each number to its
    # nearest header column.
    if anchors:

        assignments = {}

        for cell in cells:

            nearest = min(
                anchors.items(),
                key=lambda item: abs(
                    cell.cx - item[1]
                )
            )

            key, anchor_x = nearest

            # Reject implausibly distant matches.
            if abs(
                cell.cx - anchor_x
            ) <= 90:

                assignments[
                    key
                ] = cell

        return assignments

    # Fallback when no explicit headers were detected.
    assignments = {}

    if len(cells) >= 1:
        assignments[
            "per_100g"
        ] = cells[0]

    if len(cells) >= 2:
        assignments[
            "per_serving"
        ] = cells[1]

    if len(cells) >= 3:
        assignments[
            "percent_rda"
        ] = cells[2]

    return assignments


def format_nutrition_value(
    number,
    unit
):

    if number is None:
        return None

    if unit:
        return (
            f"{number}{unit}"
        )

    return number


def extract_nutrition(
    regions,
    rows
):

    nutrition = {}

    heading_rows = (
        detect_nutrition_heading_rows(
            regions
        )
    )

    anchors = detect_table_columns(
        rows,
        heading_rows
    )

    # Determine the table start.
    table_start = (
        min(
            heading_rows
        )
        if heading_rows
        else 0
    )

    for region in regions:

        # Ignore OCR far above nutrition section.
        if (
            heading_rows
            and region.row_id < table_start
        ):
            continue

        nutrient = detect_nutrient(
            region.text
        )

        if nutrient is None:
            continue

        # Nutrient labels should be on the left side.
        if region.x1 > 255:
            continue

        row = rows[
            region.row_id
        ]

        assignments = choose_numeric_cells(
            row,
            region,
            anchors
        )

        if not assignments:
            continue

        unit = nutrient_unit(
            region.text
        )

        row_result = {
            "evidence_label": region.text,
            "confidence": region.confidence,
            "box": region.box,
        }

        if "per_100g" in assignments:

            cell = assignments[
                "per_100g"
            ]

            number = extract_number(
                cell.text
            )

            row_result[
                "per_100g"
            ] = format_nutrition_value(
                number,
                unit
            )

            row_result[
                "per_100g_evidence"
            ] = cell.text

        if "per_serving" in assignments:

            cell = assignments[
                "per_serving"
            ]

            number = extract_number(
                cell.text
            )

            row_result[
                "per_serving"
            ] = format_nutrition_value(
                number,
                unit
            )

            row_result[
                "per_serving_evidence"
            ] = cell.text

        if "percent_rda" in assignments:

            cell = assignments[
                "percent_rda"
            ]

            number = extract_number(
                cell.text
            )

            if number is not None:

                row_result[
                    "percent_rda"
                ] = (
                    number
                    + "%"
                )

                row_result[
                    "percent_rda_evidence"
                ] = cell.text

        # Ignore completely empty rows.
        if any(
            key in row_result
            for key in (
                "per_100g",
                "per_serving",
                "percent_rda"
            )
        ):

            nutrition[
                nutrient
            ] = row_result

    return {
        "columns": anchors,
        "rows": nutrition,
    }


# ============================================================
# CONTACT EXTRACTION
# ============================================================

def extract_contacts(
    regions
):

    emails = []
    websites = []
    phones = []

    for region in regions:

        text = region.text

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

        # Indian mobile numbers only.
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

        # Indian landline form.
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

    return {
        "phones": phones,
        "emails": emails,
        "websites": websites,
    }


# ============================================================
# ARRANGE
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

    fields = extract_product_fields(
        regions,
        rows
    )

    fssai = extract_fssai(
        regions
    )

    if fssai:

        fields[
            "fssai_license"
        ] = {
            "values": [
                item[
                    "value"
                ]
                for item in fssai
            ],
            "evidence": fssai,
        }

    sections = extract_sections(
        regions,
        rows
    )

    nutrition = extract_nutrition(
        regions,
        rows
    )

    contacts = extract_contacts(
        regions
    )

    return {
        "success": True,

        "source_image":
            ocr_data.get(
                "image"
            ),

        "product_information":
            fields,

        "sections":
            sections,

        "nutrition":
            nutrition,

        "contacts":
            contacts,

        "layout": {
            "ocr_regions":
                len(regions),
            "visual_rows":
                len(rows),
        },

        # Preserve original evidence exactly.
        "raw_ocr":
            ocr_data.get(
                "regions",
                []
            ),
    }


# ============================================================
# OCR READER
# ============================================================

class ProductReader:

    def __init__(self):

        print(
            "=" * 70
        )

        print(
            "INITIALIZING GENERAL FOOD LABEL READER V5"
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
                enable_mkldnn=False,
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

                if i < len(scores):
                    confidence = safe_float(
                        scores[i]
                    )

                box = None

                if i < len(boxes):

                    raw_box = boxes[
                        i
                    ]

                    if hasattr(
                        raw_box,
                        "tolist"
                    ):
                        box = raw_box.tolist()
                    else:
                        box = raw_box

                regions.append(
                    {
                        "text": text,
                        "confidence":
                            confidence,
                        "box": box,
                    }
                )

        return {
            "success": True,

            "image":
                os.path.abspath(
                    image_path
                ),

            "regions":
                regions,

            "full_text":
                "\n".join(
                    r[
                        "text"
                    ]
                    for r in regions
                ),
        }


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

    else:

        for name, data in (
            fields.items()
        ):

            if name == "fssai_license":

                print(
                    f"{name:25} : "
                    f"{data.get('values', [])}"
                )

            else:

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

    else:

        for name, data in (
            sections.items()
        ):

            print()

            print(
                f"[{name.upper()}]"
            )

            for line in data[
                "content"
            ]:

                print(
                    "  " + line
                )

    print()

    print(
        "=" * 70
    )

    print(
        "NUTRITION TABLE"
    )

    print(
        "=" * 70
    )

    nutrition = result[
        "nutrition"
    ]

    if not nutrition.get(
        "rows"
    ):

        print(
            "No nutrition rows detected."
        )

    else:

        for nutrient, row in (
            nutrition[
                "rows"
            ].items()
        ):

            values = []

            for key in (
                "per_100g",
                "per_serving",
                "percent_rda"
            ):

                if key in row:
                    values.append(
                        f"{key}={row[key]}"
                    )

            print(
                f"{nutrient:25} : "
                + " | ".join(
                    values
                )
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
# IMAGE PICKER
# ============================================================

def select_image():

    root = Tk()

    root.withdraw()

    root.attributes(
        "-topmost",
        True
    )

    path = filedialog.askopenfilename(
        title="Select Product Image",

        filetypes=[
            (
                "Image files",
                "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"
            ),
            (
                "All files",
                "*.*"
            ),
        ],
    )

    root.destroy()

    return path


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print(
        "=" * 70
    )

    print(
        "GENERAL FOOD LABEL READER V5"
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

        print(
            "OCR regions:",
            len(
                ocr_result[
                    "regions"
                ]
            )
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

        final_file = os.path.join(
            output_dir,
            "product_result.json"
        )

        # ----------------------------------------------------
        # RAW OCR SAVE
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
            "Arranging information..."
        )

        # ----------------------------------------------------
        # ARRANGE
        # ----------------------------------------------------

        arranged = arrange(
            ocr_result
        )

        # ----------------------------------------------------
        # FINAL SAVE
        # ----------------------------------------------------

        with open(
            final_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                arranged,
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
            final_file
        )

        print(
            "OCR regions :",
            arranged[
                "layout"
            ][
                "ocr_regions"
            ]
        )

        print(
            "Visual rows :",
            arranged[
                "layout"
            ][
                "visual_rows"
            ]
        )

        display_result(
            arranged
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
