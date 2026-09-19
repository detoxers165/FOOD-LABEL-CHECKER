# ============================================================
# GENERAL FOOD LABEL ARRANGER - V3
# ============================================================
#
# Purpose:
# OCR output -> organized food-label information
#
# Designed for:
# - biscuits
# - chips
# - spices
# - noodles
# - juices
# - dairy products
# - sweets
# - edible oils
# - other packaged foods
#
# IMPORTANT:
# This code does NOT depend on any particular brand/product.
# ============================================================

import json
import os
import re
import sys


# ============================================================
# FIELD ALIASES
# ============================================================

FIELD_ALIASES = {
    "net_quantity": [
        "net quantity",
        "net qty",
        "net weight",
        "net wt",
        "net content",
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
        "lot code",
    ],

    "manufacturing_date": [
        "date of manufacture",
        "manufacturing date",
        "manufactured date",
        "mfg date",
        "mfg. date",
        "date of mfg",
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

    "fssai_license": [
        "fssai license",
        "fssai licence",
        "licence no",
        "licence no.",
        "license no",
        "license no.",
        "lic no",
        "lic. no",
        "fssai",
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
# SECTION HEADINGS
# ============================================================

SECTION_HEADINGS = {
    "ingredients": [
        "ingredients",
        "ingredient",
    ],

    "allergen": [
        "allergen advice",
        "allergen information",
        "allergens",
    ],

    "storage": [
        "storage instructions",
        "storage conditions",
        "storage",
    ],

    "nutrition": [
        "nutrition facts",
        "nutrition information",
        "nutritional information",
        "nutrition",
    ],
}


# ============================================================
# NUTRIENTS
# ============================================================

NUTRIENTS = [
    "energy",
    "calories",
    "protein",
    "carbohydrate",
    "carbohydrates",
    "total carbohydrate",
    "sugars",
    "total sugars",
    "added sugars",
    "fat",
    "total fat",
    "saturated fat",
    "trans fat",
    "dietary fibre",
    "dietary fiber",
    "fibre",
    "fiber",
    "sodium",
    "salt",
    "cholesterol",
    "calcium",
    "iron",
    "potassium",
]


# ============================================================
# TEXT NORMALIZATION
# ============================================================

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

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def match_text(text):
    text = normalize_text(text).lower()

    text = text.replace(".", " ")

    text = re.sub(
        r"[^a-z0-9₹$€£%:/+\- ]",
        " ",
        text
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# BOX HANDLING
# ============================================================

def box_bounds(box):
    """
    PaddleOCR rec_boxes normally look like:

        [x1, y1, x2, y2]

    Some OCR systems may return:

        [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]

    This function supports BOTH.
    """

    if box is None:
        return None

    try:

        # ----------------------------------------------------
        # Format: [x1, y1, x2, y2]
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Format: polygon
        # ----------------------------------------------------

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
        pass

    return None


def box_center(box):

    bounds = box_bounds(box)

    if bounds is None:
        return None

    x1, y1, x2, y2 = bounds

    return (
        (x1 + x2) / 2,
        (y1 + y2) / 2
    )


def box_width(box):

    bounds = box_bounds(box)

    if bounds is None:
        return 0

    return bounds[2] - bounds[0]


def box_height(box):

    bounds = box_bounds(box)

    if bounds is None:
        return 0

    return bounds[3] - bounds[1]


# ============================================================
# LABEL DETECTION
# ============================================================

def starts_with_alias(text, aliases):

    normalized = match_text(text)

    for alias in aliases:

        alias_normalized = match_text(
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
        ):
            return True

    return False


def detect_field(text):

    normalized = match_text(text)

    if not normalized:
        return None

    candidates = []

    for field, aliases in FIELD_ALIASES.items():

        for alias in aliases:

            a = match_text(alias)

            # Field labels should normally occur
            # at the START of a region.
            if (
                normalized == a
                or normalized.startswith(
                    a + " "
                )
                or normalized.startswith(
                    a + ":"
                )
                or normalized.startswith(
                    a + "-"
                )
            ):

                candidates.append(
                    (
                        len(a),
                        field
                    )
                )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    return candidates[0][1]


def detect_section(text):

    normalized = match_text(text)

    if not normalized:
        return None

    candidates = []

    for section, aliases in SECTION_HEADINGS.items():

        for alias in aliases:

            a = match_text(alias)

            if (
                normalized == a
                or normalized.startswith(
                    a + " "
                )
                or normalized.startswith(
                    a + ":"
                )
                or normalized.startswith(
                    a + "-"
                )
            ):

                candidates.append(
                    (
                        len(a),
                        section
                    )
                )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    return candidates[0][1]


# ============================================================
# DATE / NUMBER / CONTACT PATTERNS
# ============================================================

DATE_PATTERNS = [
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",

    r"\b\d{2,4}[./-]\d{1,2}[./-]\d{1,2}\b",

    r"\b\d{1,2}\s*"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"\s*\d{2,4}\b",

    r"\b\d{1,2}"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"\d{2,4}\b",
]


def contains_date(text):

    for pattern in DATE_PATTERNS:

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):
            return True

    return False


def contains_weight(text):

    return bool(
        re.search(
            r"\b\d+(?:\.\d+)?\s*"
            r"(mg|g|kg|ml|l|litre|liter|cl)\b",
            text,
            re.IGNORECASE
        )
    )


def contains_price(text):

    return bool(
        re.search(
            r"(₹|rs\.?|inr)?\s*"
            r"\d+(?:,\d{3})*(?:\.\d{1,2})?",
            text,
            re.IGNORECASE
        )
    )


def contains_license(text):

    return bool(
        re.search(
            r"\b\d{8,20}\b",
            text
        )
    )


def contains_batch_code(text):

    text = text.strip()

    # Avoid long sentences.
    if len(text) > 40:
        return False

    # Typical batch/lot code:
    # K26G7006
    # AB1234
    # 123456789
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9./_-]{4,25}",
            text
        )
    )


def extract_email(text):

    found = re.findall(
        r"\b[A-Z0-9._%+-]+"
        r"@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        text,
        re.IGNORECASE
    )

    return found


def extract_websites(text):

    found = re.findall(
        r"(?:https?://|www\.)[^\s]+",
        text,
        re.IGNORECASE
    )

    return found


# ============================================================
# PHONE EXTRACTION
# ============================================================

def extract_phones(text):

    results = []

    # Indian mobile numbers.
    mobile_matches = re.findall(
        r"(?<!\d)"
        r"(?:\+91[\s-]?)?"
        r"[6-9]\d{9}"
        r"(?!\d)",
        text
    )

    for number in mobile_matches:

        if number not in results:
            results.append(number)

    # Indian landline style:
    # +91-151-2250350
    landline_matches = re.findall(
        r"\+91[\s-]?"
        r"\d{2,5}[\s-]"
        r"\d{5,8}",
        text
    )

    for number in landline_matches:

        if number not in results:
            results.append(number)

    # Toll-free / common 1800-style numbers.
    toll_matches = re.findall(
        r"\b1800[\s-]?\d{3,7}\b",
        text
    )

    for number in toll_matches:

        if number not in results:
            results.append(number)

    return results


# ============================================================
# INLINE VALUE EXTRACTION
# ============================================================

def extract_after_alias(text, aliases):

    original = normalize_text(
        text
    )

    for alias in aliases:

        pattern = re.compile(
            r"^\s*"
            + re.escape(
                normalize_text(alias)
            )
            + r"\s*[:\-]?\s*(.+)$",
            re.IGNORECASE
        )

        match = pattern.search(
            original
        )

        if match:

            value = match.group(1).strip()

            if value:
                return value

    return None


def extract_special_inline_value(
    text,
    field
):

    if field == "email":

        emails = extract_email(text)

        if emails:
            return emails[0]

        return None

    if field == "website":

        websites = extract_websites(text)

        if websites:
            return websites[0]

        return None

    return extract_after_alias(
        text,
        FIELD_ALIASES[field]
    )


# ============================================================
# VALUE VALIDATION
# ============================================================

def value_valid(field, value):

    if not value:
        return False

    value = value.strip()

    # Another obvious label is probably not a value.
    if detect_field(value) is not None:
        return False

    if detect_section(value) is not None:
        return False

    if field == "net_quantity":
        return contains_weight(value)

    if field == "mrp":
        return contains_price(value)

    if field in (
        "manufacturing_date",
        "expiry_date"
    ):
        return contains_date(value)

    if field == "fssai_license":
        return contains_license(value)

    if field == "batch_number":
        return contains_batch_code(value)

    if field == "email":
        return bool(
            extract_email(value)
        )

    if field == "website":
        return bool(
            extract_websites(value)
        )

    return True


# ============================================================
# SPATIAL MATCHING
# ============================================================

def spatial_score(
    label_region,
    value_region,
    field
):

    lb = box_bounds(
        label_region.get("box")
    )

    vb = box_bounds(
        value_region.get("box")
    )

    if lb is None or vb is None:
        return -1

    lx1, ly1, lx2, ly2 = lb
    vx1, vy1, vx2, vy2 = vb

    label_center = box_center(lb)
    value_center = box_center(vb)

    if label_center is None or value_center is None:
        return -1

    lx, ly = label_center
    vx, vy = value_center

    label_height = max(
        box_height(lb),
        8
    )

    label_width = max(
        box_width(lb),
        10
    )

    dx = vx - lx
    dy = vy - ly

    score = 0

    # --------------------------------------------------------
    # SAME ROW - VALUE TO RIGHT
    # --------------------------------------------------------

    if vx >= lx:

        vertical_gap = abs(
            vy - ly
        )

        if vertical_gap <= label_height * 2.0:

            horizontal_gap = max(
                0,
                vx1 - lx2
            )

            if horizontal_gap <= 500:

                score += 1200

                score -= (
                    vertical_gap * 4
                )

                score -= (
                    horizontal_gap * 0.5
                )

    # --------------------------------------------------------
    # SAME ROW - VALUE TO LEFT
    # Some labels may appear after values.
    # --------------------------------------------------------

    if vx < lx:

        vertical_gap = abs(
            vy - ly
        )

        if vertical_gap <= label_height * 2.0:

            horizontal_gap = max(
                0,
                lx1 - vx2
            )

            if horizontal_gap <= 300:

                score += 800

                score -= (
                    vertical_gap * 4
                )

                score -= (
                    horizontal_gap * 0.5
                )

    # --------------------------------------------------------
    # BELOW LABEL
    # --------------------------------------------------------

    if vy >= ly:

        vertical_gap = max(
            0,
            vy1 - ly2
        )

        horizontal_gap = abs(
            vx - lx
        )

        if (
            vertical_gap <= 180
            and horizontal_gap <= max(
                250,
                label_width * 4
            )
        ):

            score += 750

            score -= (
                vertical_gap * 2
            )

            score -= (
                horizontal_gap * 1.2
            )

    # --------------------------------------------------------
    # FIELD-SPECIFIC VALIDATION
    # --------------------------------------------------------

    candidate_text = value_region[
        "text"
    ].strip()

    if value_valid(
        field,
        candidate_text
    ):

        score += 1000

    else:

        score -= 700

    return score


# ============================================================
# FIND VALUE
# ============================================================

def find_value_for_label(
    label_index,
    label_region,
    regions,
    used_indices
):

    field = detect_field(
        label_region["text"]
    )

    if field is None:
        return None

    candidates = []

    for index, region in enumerate(
        regions
    ):

        if index == label_index:
            continue

        if index in used_indices:
            continue

        text = str(
            region.get(
                "text",
                ""
            )
        ).strip()

        if not text:
            continue

        # Another label should not become our value.
        if detect_field(text) is not None:
            continue

        # Another section heading should not become value.
        if detect_section(text) is not None:
            continue

        score = spatial_score(
            label_region,
            region,
            field
        )

        if score > 0:

            candidates.append(
                (
                    score,
                    index,
                    region
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    return candidates[0]


# ============================================================
# PRODUCT FIELD EXTRACTION
# ============================================================

def extract_product_fields(
    regions
):

    fields = {}

    used_indices = set()

    for index, region in enumerate(
        regions
    ):

        text = str(
            region.get(
                "text",
                ""
            )
        ).strip()

        if not text:
            continue

        field = detect_field(
            text
        )

        if field is None:
            continue

        # ----------------------------------------------------
        # FIRST: inline value
        # ----------------------------------------------------

        inline_value = (
            extract_special_inline_value(
                text,
                field
            )
        )

        if (
            inline_value
            and value_valid(
                field,
                inline_value
            )
        ):

            save_field(
                fields,
                field,
                inline_value,
                region,
                region
            )

            continue

        # ----------------------------------------------------
        # SECOND: spatial value
        # ----------------------------------------------------

        result = find_value_for_label(
            index,
            region,
            regions,
            used_indices
        )

        if result is None:

            save_field(
                fields,
                field,
                None,
                region,
                None
            )

            continue

        score, value_index, value_region = (
            result
        )

        value = str(
            value_region.get(
                "text",
                ""
            )
        ).strip()

        if not value_valid(
            field,
            value
        ):

            save_field(
                fields,
                field,
                None,
                region,
                None
            )

            continue

        used_indices.add(
            value_index
        )

        save_field(
            fields,
            field,
            value,
            region,
            value_region
        )

    return fields


# ============================================================
# SAVE FIELD
# ============================================================

def save_field(
    fields,
    field,
    value,
    label_region,
    value_region
):

    entry = {
        "value": value,
        "label": label_region.get(
            "text"
        ),
        "label_confidence":
            label_region.get(
                "confidence"
            ),
        "label_box":
            label_region.get(
                "box"
            ),
        "evidence": [
            label_region.get(
                "text"
            )
        ]
    }

    if value_region is not None:

        if value_region is not label_region:

            entry[
                "value_confidence"
            ] = value_region.get(
                "confidence"
            )

            entry[
                "value_box"
            ] = value_region.get(
                "box"
            )

            entry["evidence"].append(
                value_region.get(
                    "text"
                )
            )

    if field not in fields:

        fields[field] = entry

        return

    existing = fields[field]

    if (
        value
        and existing.get("value") is None
    ):

        fields[field] = entry

        return

    if (
        value
        and value != existing.get(
            "value"
        )
    ):

        if (
            "additional_values"
            not in existing
        ):

            existing[
                "additional_values"
            ] = []

        if value not in existing[
            "additional_values"
        ]:

            existing[
                "additional_values"
            ].append(value)

            existing[
                "evidence"
            ].extend(
                entry[
                    "evidence"
                ]
            )


# ============================================================
# SECTION INLINE EXTRACTION
# ============================================================

def section_inline_content(
    text,
    section
):

    original = normalize_text(
        text
    )

    aliases = SECTION_HEADINGS[
        section
    ]

    for alias in aliases:

        pattern = re.compile(
            r"^\s*"
            + re.escape(
                normalize_text(alias)
            )
            + r"\s*[:\-]?\s*(.*)$",
            re.IGNORECASE
        )

        match = pattern.search(
            original
        )

        if match:

            content = (
                match.group(1)
                .strip()
            )

            if content:
                return content

    return None


# ============================================================
# SECTION EXTRACTION
# ============================================================

def extract_sections(
    regions
):

    sections = {}

    for index, region in enumerate(
        regions
    ):

        text = str(
            region.get(
                "text",
                ""
            )
        ).strip()

        section = detect_section(
            text
        )

        if section is None:
            continue

        content = []

        # ----------------------------------------------------
        # Content already in same OCR region
        # ----------------------------------------------------

        inline = section_inline_content(
            text,
            section
        )

        if inline:
            content.append(
                inline
            )

        # ----------------------------------------------------
        # Collect nearby following text
        # ----------------------------------------------------

        heading_center = box_center(
            region.get("box")
        )

        if heading_center is None:

            if content:
                sections[section] = {
                    "heading": text,
                    "content": content,
                    "confidence":
                        region.get(
                            "confidence"
                        ),
                    "box":
                        region.get(
                            "box"
                        )
                }

            continue

        hx, hy = heading_center

        for next_region in regions[
            index + 1:
        ]:

            next_text = str(
                next_region.get(
                    "text",
                    ""
                )
            ).strip()

            if not next_text:
                continue

            next_section = detect_section(
                next_text
            )

            if next_section is not None:
                break

            next_field = detect_field(
                next_text
            )

            # Stop when another metadata block begins.
            if next_field is not None:
                break

            center = box_center(
                next_region.get("box")
            )

            if center is None:
                continue

            nx, ny = center

            if ny < hy:
                continue

            if ny - hy > 350:
                break

            # Keep content in the same local block.
            if abs(nx - hx) > 450:
                continue

            content.append(
                next_text
            )

            if len(content) >= 15:
                break

        # Remove duplicates while keeping order.
        cleaned = []

        for item in content:

            item = item.strip()

            if (
                item
                and item not in cleaned
            ):
                cleaned.append(item)

        if cleaned:

            sections[section] = {
                "heading": text,
                "content": cleaned,
                "confidence":
                    region.get(
                        "confidence"
                    ),
                "box":
                    region.get(
                        "box"
                    )
            }

    return sections


# ============================================================
# NUTRITION
# ============================================================

def nutrient_name(text):

    normalized = match_text(
        text
    )

    matches = []

    for nutrient in NUTRIENTS:

        n = match_text(
            nutrient
        )

        # Nutrient should occur near the beginning.
        if (
            normalized == n
            or normalized.startswith(
                n + " "
            )
            or normalized.startswith(
                n + "/"
            )
            or normalized.startswith(
                n + ":"
            )
        ):

            matches.append(
                (
                    len(n),
                    nutrient
                )
            )

    if not matches:
        return None

    matches.sort(
        reverse=True
    )

    return matches[0][1]


def numeric_values(text):

    return re.findall(
        r"\b\d+(?:\.\d+)?\s*"
        r"(?:mg|g|kg|ml|kcal|kj|%)?\b",
        text,
        re.IGNORECASE
    )


def extract_nutrition(
    regions
):

    nutrition = {}

    # Only consider regions where the nutrient
    # appears as the beginning of the OCR text.
    for index, region in enumerate(
        regions
    ):

        text = str(
            region.get(
                "text",
                ""
            )
        ).strip()

        nutrient = nutrient_name(
            text
        )

        if nutrient is None:
            continue

        values = numeric_values(
            text
        )

        # ----------------------------------------------------
        # Nutrient and value are in SAME OCR region
        # ----------------------------------------------------

        if values:

            selected = None

            for value in values:

                number_match = re.search(
                    r"\d+(?:\.\d+)?",
                    value
                )

                if not number_match:
                    continue

                try:
                    number = float(
                        number_match.group()
                    )
                except Exception:
                    continue

                if nutrient in (
                    "energy",
                    "calories"
                ):

                    if (
                        0 < number <= 5000
                    ):
                        selected = value
                        break

                else:

                    if (
                        0 < number <= 1000
                    ):
                        selected = value
                        break

            if selected:

                nutrition[nutrient] = {
                    "value":
                        selected,
                    "evidence":
                        text,
                    "confidence":
                        region.get(
                            "confidence"
                        ),
                    "box":
                        region.get(
                            "box"
                        )
                }

                continue

        # ----------------------------------------------------
        # Find nearby numeric OCR region
        # ----------------------------------------------------

        candidates = []

        for j, other in enumerate(
            regions
        ):

            if j == index:
                continue

            other_text = str(
                other.get(
                    "text",
                    ""
                )
            ).strip()

            values = numeric_values(
                other_text
            )

            if not values:
                continue

            score = spatial_score(
                region,
                other,
                "nutrition"
            )

            if score > 0:

                candidates.append(
                    (
                        score,
                        other,
                        values[0]
                    )
                )

        if candidates:

            candidates.sort(
                key=lambda x: x[0],
                reverse=True
            )

            _, best, value = (
                candidates[0]
            )

            nutrition[nutrient] = {
                "value":
                    value,
                "evidence": [
                    text,
                    best.get(
                        "text"
                    )
                ],
                "confidence":
                    best.get(
                        "confidence"
                    ),
                "box":
                    best.get(
                        "box"
                    )
            }

    return nutrition


# ============================================================
# CONTACT EXTRACTION
# ============================================================

def extract_contacts(
    regions
):

    contacts = {
        "phones": [],
        "emails": [],
        "websites": []
    }

    for region in regions:

        text = str(
            region.get(
                "text",
                ""
            )
        ).strip()

        for email in extract_email(
            text
        ):

            if email not in contacts[
                "emails"
            ]:

                contacts[
                    "emails"
                ].append(email)

        for website in extract_websites(
            text
        ):

            if website not in contacts[
                "websites"
            ]:

                contacts[
                    "websites"
                ].append(website)

        for phone in extract_phones(
            text
        ):

            if phone not in contacts[
                "phones"
            ]:

                contacts[
                    "phones"
                ].append(phone)

    return contacts


# ============================================================
# MAIN ARRANGEMENT
# ============================================================

def arrange(
    ocr_data
):

    regions = []

    for region in ocr_data.get(
        "regions",
        []
    ):

        text = str(
            region.get(
                "text",
                ""
            )
        ).strip()

        if not text:
            continue

        regions.append(
            region
        )

    product_information = (
        extract_product_fields(
            regions
        )
    )

    sections = extract_sections(
        regions
    )

    nutrition = extract_nutrition(
        regions
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
            product_information,

        "sections":
            sections,

        "nutrition":
            nutrition,

        "contacts":
            contacts,

        "raw_ocr":
            regions
    }


# ============================================================
# DISPLAY
# ============================================================

def display_result(
    result
):

    print()
    print("=" * 70)
    print(
        "STRUCTURED PRODUCT INFORMATION"
    )
    print("=" * 70)

    fields = result[
        "product_information"
    ]

    for field, data in fields.items():

        print(
            f"{field:25} : "
            f"{data.get('value')}"
        )

        if data.get(
            "additional_values"
        ):

            print(
                " " * 27
                + "Additional: "
                + ", ".join(
                    str(x)
                    for x in data[
                        "additional_values"
                    ]
                )
            )

    print()
    print("=" * 70)
    print("SECTIONS")
    print("=" * 70)

    sections = result[
        "sections"
    ]

    if not sections:

        print("No sections detected.")

    else:

        for name, data in sections.items():

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
    print("=" * 70)
    print("NUTRITION")
    print("=" * 70)

    nutrition = result[
        "nutrition"
    ]

    if not nutrition:

        print("No nutrition data detected.")

    else:

        for nutrient, data in nutrition.items():

            print(
                f"{nutrient:25} : "
                f"{data.get('value')}"
            )

    print()
    print("=" * 70)
    print("CONTACT INFORMATION")
    print("=" * 70)

    contacts = result[
        "contacts"
    ]

    print(
        "Phones   :",
        contacts["phones"]
    )

    print(
        "Emails   :",
        contacts["emails"]
    )

    print(
        "Websites :",
        contacts["websites"]
    )

    print()


# ============================================================
# PROGRAM ENTRY
# ============================================================

def main():

    print()
    print("=" * 70)
    print("GENERAL FOOD LABEL ARRANGER V3")
    print("=" * 70)
    print()

    project_root = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

    input_file = os.path.join(
        project_root,
        "output",
        "ocr_result.json"
    )

    output_file = os.path.join(
        project_root,
        "output",
        "arranged_result.json"
    )

    if not os.path.isfile(
        input_file
    ):

        print(
            "ERROR: OCR result not found:"
        )

        print(input_file)

        sys.exit(1)

    try:

        with open(
            input_file,
            "r",
            encoding="utf-8"
        ) as file:

            ocr_data = json.load(
                file
            )

    except Exception as e:

        print(
            "ERROR: Could not read OCR JSON."
        )

        print(str(e))

        sys.exit(1)

    print(
        "OCR regions:",
        len(
            ocr_data.get(
                "regions",
                []
            )
        )
    )

    print()
    print(
        "Arranging OCR using corrected "
        "bounding-box relationships..."
    )
    print()

    result = arrange(
        ocr_data
    )

    os.makedirs(
        os.path.dirname(
            output_file
        ),
        exist_ok=True
    )

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

    print(
        "Arrangement complete."
    )

    print(
        "Product fields:",
        len(
            result[
                "product_information"
            ]
        )
    )

    print(
        "Sections:",
        len(
            result[
                "sections"
            ]
        )
    )

    print(
        "Nutrition fields:",
        len(
            result[
                "nutrition"
            ]
        )
    )

    print()
    print(
        "Output:",
        output_file
    )

    display_result(
        result
    )


if __name__ == "__main__":
    main()