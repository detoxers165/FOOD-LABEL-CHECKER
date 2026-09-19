# ============================================================
# GENERAL FOOD LABEL READER V4
# ============================================================
# Image -> PaddleOCR -> spatial arranger -> structured JSON
# Generic: no brand/product-specific coordinates or assumptions.
# ============================================================

import json
import os
import re
import sys
from dataclasses import dataclass
from tkinter import Tk, filedialog

# -------------------------------------------------------------------
# PaddleOCR compatibility / safe CPU settings used by the working setup
# -------------------------------------------------------------------
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")

try:
    from paddleocr import PaddleOCR
except Exception as exc:
    print("ERROR: Could not import PaddleOCR.")
    print(str(exc))
    sys.exit(1)


# ============================================================
# CONFIGURATION
# ============================================================

FIELD_ALIASES = {
    "net_quantity": [
        "net quantity", "net qty", "net weight", "net wt",
        "net content", "net contents"
    ],
    "mrp": [
        "maximum retail price", "max retail price",
        "maximum retail selling price", "mrp"
    ],
    "batch_number": [
        "batch number", "batch no", "batch no.", "batch code",
        "lot number", "lot no", "lot no.", "lot code"
    ],
    "manufacturing_date": [
        "date of manufacture", "manufacturing date",
        "manufactured date", "mfg date", "mfg. date",
        "date of mfg", "packed on", "packing date"
    ],
    "expiry_date": [
        "expiry date", "expiration date", "exp date", "exp. date",
        "use by", "use before", "best before"
    ],
    "fssai_license": [
        "fssai license", "fssai licence", "licence no", "licence no.",
        "license no", "license no.", "lic no", "lic. no"
    ],
    "manufacturer": [
        "manufactured by", "manufactured for", "manufacturer",
        "mfd by", "mfd. by"
    ],
    "marketed_by": [
        "marketed by", "marketed for"
    ],
    "customer_care": [
        "customer care", "consumer care", "customer service",
        "consumer service", "contact us", "helpline", "help line"
    ],
}

SECTION_ALIASES = {
    "ingredients": ["ingredients", "ingredient"],
    "allergen": ["allergen advice", "allergen information", "allergens"],
    "storage": ["storage instructions", "storage conditions", "storage"],
    "nutrition": [
        "nutrition facts", "nutrition information",
        "nutritional information", "nutrition information"
    ],
}

NUTRIENT_ALIASES = [
    "energy", "calories", "protein", "total protein",
    "carbohydrate", "carbohydrates", "total carbohydrate",
    "sugars", "total sugars", "added sugars",
    "fat", "total fat", "saturated fat", "trans fat",
    "dietary fibre", "dietary fiber", "fibre", "fiber",
    "sodium", "salt", "cholesterol", "calcium", "iron", "potassium"
]

# Words that should never become a generic metadata value.
BAD_VALUE_WORDS = {
    "advice", "information", "facts", "instructions", "conditions",
    "none", "n/a", "na", "unknown"
}


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
# TEXT HELPERS
# ============================================================

def normalize_text(text: str) -> str:
    text = str(text)
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.replace("：", ":").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def match_text(text: str) -> str:
    text = normalize_text(text).lower()
    text = text.replace(".", " ")
    text = re.sub(r"[^a-z0-9₹%:/+\- ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_text(text).lower())


def alias_matches_start(text: str, aliases: list[str]) -> tuple[int, str] | None:
    normalized = match_text(text)
    for alias in sorted(aliases, key=lambda x: len(match_text(x)), reverse=True):
        a = match_text(alias)
        if not a:
            continue
        if normalized == a or normalized.startswith(a + " ") or normalized.startswith(a + ":") or normalized.startswith(a + "-"):
            return len(a), alias
    return None


def detect_field(text: str) -> str | None:
    hits = []
    for field, aliases in FIELD_ALIASES.items():
        hit = alias_matches_start(text, aliases)
        if hit:
            hits.append((hit[0], field))
    if not hits:
        return None
    return max(hits)[1]


def detect_section(text: str) -> str | None:
    hits = []
    for section, aliases in SECTION_ALIASES.items():
        hit = alias_matches_start(text, aliases)
        if hit:
            hits.append((hit[0], section))
    if not hits:
        return None
    return max(hits)[1]


def detect_nutrient(text: str) -> str | None:
    normalized = match_text(text)
    hits = []
    for nutrient in NUTRIENT_ALIASES:
        n = match_text(nutrient)
        if normalized == n or normalized.startswith(n + " ") or normalized.startswith(n + ":") or normalized.startswith(n + "/"):
            hits.append((len(n), nutrient))
    if not hits:
        return None
    return max(hits)[1]


# ============================================================
# BOX HELPERS
# ============================================================

def parse_box(box):
    """Supports PaddleOCR rec_boxes [x1,y1,x2,y2] and polygons."""
    if box is None:
        return None
    try:
        if isinstance(box, (list, tuple)) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
            x1, y1, x2, y2 = map(float, box)
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            return x1, y1, x2, y2
        xs, ys = [], []
        for p in box:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
        if xs and ys:
            return min(xs), min(ys), max(xs), max(ys)
    except Exception:
        return None
    return None


def make_regions(ocr_data: dict) -> list[Region]:
    regions = []
    for i, raw in enumerate(ocr_data.get("regions", [])):
        text = normalize_text(raw.get("text", ""))
        bounds = parse_box(raw.get("box"))
        if not text or bounds is None:
            continue
        x1, y1, x2, y2 = bounds
        regions.append(
            Region(
                index=i,
                text=text,
                confidence=safe_float(raw.get("confidence")),
                box=raw.get("box"),
                x1=x1, y1=y1, x2=x2, y2=y2,
                cx=(x1 + x2) / 2,
                cy=(y1 + y2) / 2,
                width=max(1.0, x2 - x1),
                height=max(1.0, y2 - y1),
            )
        )
    return regions


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def median(values: list[float], default: float) -> float:
    if not values:
        return default
    values = sorted(values)
    n = len(values)
    mid = n // 2
    if n % 2:
        return float(values[mid])
    return (values[mid - 1] + values[mid]) / 2.0


# ============================================================
# ROW DETECTION
# ============================================================

def build_rows(regions: list[Region]) -> list[list[Region]]:
    """Cluster OCR regions into local visual rows."""
    if not regions:
        return []

    ordered = sorted(regions, key=lambda r: (r.cy, r.x1))
    median_h = median([r.height for r in regions], 20.0)
    tolerance = max(8.0, min(28.0, median_h * 0.65))

    rows: list[list[Region]] = []
    row_centers: list[float] = []

    for region in ordered:
        best = -1
        best_diff = float("inf")
        for i, center in enumerate(row_centers):
            diff = abs(region.cy - center)
            if diff <= tolerance and diff < best_diff:
                best = i
                best_diff = diff

        if best == -1:
            rows.append([region])
            row_centers.append(region.cy)
            continue

        rows[best].append(region)
        row_centers[best] = sum(r.cy for r in rows[best]) / len(rows[best])

    # Sort and assign stable row ids.
    pairs = sorted(zip(row_centers, rows), key=lambda x: x[0])
    result = []
    for rid, (_, row) in enumerate(pairs):
        row.sort(key=lambda r: r.x1)
        for r in row:
            r.row_id = rid
        result.append(row)
    return result


# ============================================================
# PATTERNS / VALIDATORS
# ============================================================

DATE_PATTERNS = [
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
    r"\b\d{2,4}[./-]\d{1,2}[./-]\d{1,2}\b",
    r"\b\d{1,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{2,4}\b",
    r"\b\d{1,2}(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\d{2,4}\b",
]


def has_date(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in DATE_PATTERNS)


def date_extract(text: str) -> str | None:
    for p in DATE_PATTERNS:
        m = re.search(p, text, re.I)
        if m:
            return m.group(0)
    return None


def weight_extract(text: str) -> str | None:
    m = re.search(
        r"\b\d+(?:\.\d+)?\s*(?:mg|g|kg|ml|l|litre|liter|cl)\b",
        text, re.I
    )
    return m.group(0) if m else None


def price_extract(text: str) -> str | None:
    """Accept plain price tokens; reject USP/cost-per-unit strings."""
    cleaned = normalize_text(text)
    # First prefer currency + number.
    m = re.search(r"(?:₹|rs\.?|inr)\s*\d+(?:,\d{3})*(?:\.\d{1,2})?", cleaned, re.I)
    if m:
        return m.group(0).strip()
    # Or a region that is essentially only a number.
    if re.fullmatch(r"\s*\d+(?:\.\d{1,2})?\s*", cleaned):
        return cleaned.strip()
    return None


def license_numbers(text: str) -> list[str]:
    # Licence numbers normally occur after licence/FSSAI wording.
    return re.findall(r"\b\d{8,20}\b", text)


def batch_extract(text: str) -> str | None:
    cleaned = normalize_text(text).strip(" :.-")
    if not cleaned or len(cleaned) > 30:
        return None
    if cleaned.lower() in BAD_VALUE_WORDS:
        return None
    # Typical batch/lot identifiers. Avoid ordinary words.
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{3,24}", cleaned):
        if any(c.isdigit() for c in cleaned) or any(c.isalpha() for c in cleaned):
            return cleaned
    return None


def meaningful_value(text: str) -> bool:
    s = normalize_text(text).strip(" :.-")
    if len(s) < 2:
        return False
    if s.lower() in BAD_VALUE_WORDS:
        return False
    return bool(re.search(r"[A-Za-z0-9]", s))


def field_value_extract(field: str, text: str) -> str | list[str] | None:
    s = normalize_text(text)
    if field == "net_quantity":
        return weight_extract(s)
    if field == "mrp":
        return price_extract(s)
    if field in ("manufacturing_date", "expiry_date"):
        return date_extract(s)
    if field == "fssai_license":
        nums = license_numbers(s)
        return nums if nums else None
    if field == "batch_number":
        return batch_extract(s)
    if field in ("manufacturer", "marketed_by"):
        # Reject punctuation-only OCR; otherwise retain original text.
        return s if meaningful_value(s) else None
    return s if meaningful_value(s) else None


# ============================================================
# INLINE LABEL + VALUE
# ============================================================

def remove_alias_prefix(text: str, aliases: list[str]) -> str | None:
    s = normalize_text(text)
    for alias in sorted(aliases, key=len, reverse=True):
        pattern = r"^\s*" + re.escape(normalize_text(alias)) + r"\s*(?::|-)?\s*(.*)$"
        m = re.match(pattern, s, re.I)
        if m:
            rest = m.group(1).strip()
            return rest if rest else None
    return None


def inline_value(field: str, region_text: str):
    rest = remove_alias_prefix(region_text, FIELD_ALIASES[field])
    if rest is None:
        return None
    value = field_value_extract(field, rest)
    if isinstance(value, list):
        return value if value else None
    return value


# ============================================================
# CANDIDATE SCORING
# ============================================================

def same_row_score(label: Region, candidate: Region, field: str) -> float:
    # Only compare near-horizontal regions.
    y_gap = abs(candidate.cy - label.cy)
    row_scale = max(label.height, candidate.height, 10.0)
    if y_gap > row_scale * 1.25:
        return -1

    # Do not cross a large horizontal gap.
    if candidate.x1 >= label.x2:
        gap = candidate.x1 - label.x2
        if gap > max(250.0, label.width * 5):
            return -1
        direction_bonus = 1000.0
        horizontal_penalty = gap * 1.3
    else:
        gap = label.x1 - candidate.x2
        if gap > 180:
            return -1
        direction_bonus = 450.0
        horizontal_penalty = gap * 1.8

    extracted = field_value_extract(field, candidate.text)
    if extracted is None:
        return -1

    return direction_bonus - horizontal_penalty - y_gap * 5.0


def below_score(label: Region, candidate: Region, field: str) -> float:
    # Candidate must actually be below the label.
    vertical_gap = candidate.y1 - label.y2
    if vertical_gap < -5:
        return -1
    if vertical_gap > 220:
        return -1

    # Candidate should sit in/near the label's horizontal block.
    horizontal_gap = abs(candidate.cx - label.cx)
    horizontal_limit = max(220.0, label.width * 4.5)
    if horizontal_gap > horizontal_limit:
        return -1

    extracted = field_value_extract(field, candidate.text)
    if extracted is None:
        return -1

    return 700.0 - vertical_gap * 2.2 - horizontal_gap * 1.2


def find_spatial_value(label: Region, field: str, rows: list[list[Region]], used: set[int]):
    # 1) Prefer same-row relationships.
    row = rows[label.row_id] if 0 <= label.row_id < len(rows) else []
    candidates = []
    for candidate in row:
        if candidate.index == label.index or candidate.index in used:
            continue
        if detect_field(candidate.text) is not None:
            continue
        score = same_row_score(label, candidate, field)
        if score > 0:
            candidates.append((score, candidate))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0]

    # 2) Then look below, but only a small number of rows.
    start = label.row_id + 1
    end = min(len(rows), start + 4)
    for row_id in range(start, end):
        row_candidates = []
        for candidate in rows[row_id]:
            if candidate.index in used:
                continue
            if detect_field(candidate.text) is not None:
                continue
            score = below_score(label, candidate, field)
            if score > 0:
                row_candidates.append((score, candidate))
        if row_candidates:
            row_candidates.sort(key=lambda x: x[0], reverse=True)
            return row_candidates[0]

    return None


# ============================================================
# FSSAI-SPECIFIC LOCAL EXTRACTION
# ============================================================

def collect_fssai(regions: list[Region], rows: list[list[Region]]):
    entries = []
    seen = set()

    for r in regions:
        text_m = match_text(r.text)
        # We only trigger on actual FSSAI/licence wording.
        if "fssai" not in text_m and not re.search(r"\blic(?:ence|ense)?\s+no", text_m):
            continue

        nums = license_numbers(r.text)
        for n in nums:
            if n not in seen:
                entries.append({
                    "value": n,
                    "evidence": [r.text],
                    "confidence": r.confidence,
                    "box": r.box,
                })
                seen.add(n)

        # Search same row and one row below for a pure number region.
        row = rows[r.row_id] if 0 <= r.row_id < len(rows) else []
        nearby = list(row)
        if r.row_id + 1 < len(rows):
            nearby += rows[r.row_id + 1]

        for c in nearby:
            if c.index == r.index:
                continue
            nums = license_numbers(c.text)
            # Avoid treating ordinary descriptive text as a licence.
            if nums and len(c.text.strip()) <= 35:
                for n in nums:
                    if n not in seen:
                        entries.append({
                            "value": n,
                            "evidence": [r.text, c.text],
                            "confidence": c.confidence,
                            "box": c.box,
                        })
                        seen.add(n)

    return entries


# ============================================================
# PRODUCT FIELD EXTRACTION
# ============================================================

def extract_product_fields(regions, rows):
    fields = {}
    used = set()

    for r in regions:
        field = detect_field(r.text)
        if field is None or field == "fssai_license":
            continue

        # Never use a heading-only token as a value.
        value = inline_value(field, r.text)
        value_region = r if value is not None else None

        if value is None:
            result = find_spatial_value(r, field, rows, used)
            if result:
                _, candidate = result
                value = field_value_extract(field, candidate.text)
                if value is not None:
                    value_region = candidate
                    used.add(candidate.index)

        entry = {
            "value": value,
            "label": r.text,
            "label_confidence": r.confidence,
            "label_box": r.box,
            "evidence": [r.text],
        }

        if value_region is not None and value_region.index != r.index:
            entry["value_confidence"] = value_region.confidence
            entry["value_box"] = value_region.box
            entry["evidence"].append(value_region.text)

        if field not in fields:
            fields[field] = entry
        else:
            # Keep later valid distinct values instead of overwriting evidence.
            existing = fields[field]
            if existing.get("value") is None and value is not None:
                fields[field] = entry
            elif value is not None and value != existing.get("value"):
                existing.setdefault("additional_values", [])
                vals = value if isinstance(value, list) else [value]
                for v in vals:
                    if v not in existing["additional_values"]:
                        existing["additional_values"].append(v)
                        existing["evidence"].extend(entry["evidence"])

    # Replace generic FSSAI result with dedicated multi-licence extraction.
    fssai = collect_fssai(regions, rows)
    if fssai:
        fields["fssai_license"] = {
            "values": [x["value"] for x in fssai],
            "evidence": fssai,
        }
    else:
        # Keep the field visible when the label existed but number wasn't found.
        has_label = any(
            "fssai" in match_text(r.text) or
            re.search(r"\blic(?:ence|ense)?\s+no", match_text(r.text))
            for r in regions
        )
        if has_label:
            fields["fssai_license"] = {
                "values": [],
                "evidence": []
            }

    return fields


# ============================================================
# SECTION ARRANGER
# ============================================================

def extract_sections(regions, rows):
    sections = {}

    for r in regions:
        section = detect_section(r.text)
        if section is None:
            continue

        content = []
        inline = remove_alias_prefix(r.text, SECTION_ALIASES[section])
        if inline:
            content.append(inline)

        # Collect text immediately below, with local x alignment.
        for row_id in range(r.row_id + 1, min(len(rows), r.row_id + 8)):
            row = rows[row_id]
            stop = False
            row_items = []
            for c in row:
                if detect_section(c.text) is not None:
                    stop = True
                    break
                if detect_field(c.text) is not None:
                    stop = True
                    break

                # Local block: overlapping x-range or reasonably close center.
                overlap = min(r.x2, c.x2) - max(r.x1, c.x1)
                close = abs(c.cx - r.cx) <= max(350.0, r.width * 4)
                if overlap > -40 or close:
                    row_items.append(c.text)

            if stop:
                break
            if row_items:
                content.extend(row_items)

        cleaned = []
        for item in content:
            item = normalize_text(item)
            if item and item not in cleaned:
                cleaned.append(item)

        if cleaned:
            sections[section] = {
                "heading": r.text,
                "content": cleaned,
                "confidence": r.confidence,
                "box": r.box,
            }

    return sections


# ============================================================
# NUTRITION ARRANGER
# ============================================================

def nutrient_value_allowed(nutrient: str, text: str) -> bool:
    t = text.lower()
    if nutrient in ("energy", "calories"):
        return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:kcal|kj)\b", t, re.I))
    if nutrient in ("sodium", "calcium", "iron"):
        return bool(re.search(r"\b\d+(?:\.\d+)?\s*mg\b", t, re.I))
    if nutrient in ("protein", "carbohydrate", "carbohydrates", "total carbohydrate", "sugars", "total sugars", "added sugars", "fat", "total fat", "saturated fat", "trans fat", "dietary fibre", "dietary fiber", "fibre", "fiber", "salt", "potassium"):
        return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|g|kg)\b", t, re.I))
    if nutrient == "cholesterol":
        return bool(re.search(r"\b\d+(?:\.\d+)?\s*mg\b", t, re.I))
    return False


def extract_nutrition(regions, rows):
    result = {}

    # Prefer nutrient regions that sit within/under a detected nutrition heading.
    nutrition_heading_rows = {
        r.row_id for r in regions if detect_section(r.text) == "nutrition"
    }

    for r in regions:
        nutrient = detect_nutrient(r.text)
        if nutrient is None:
            continue

        # Avoid random sentences containing "energy" etc.
        if nutrition_heading_rows and r.row_id + 12 < min(nutrition_heading_rows):
            continue

        # Same region first.
        nums = re.findall(
            r"\b\d+(?:\.\d+)?\s*(?:mg|g|kg|ml|kcal|kj|%)?\b",
            r.text,
            re.I,
        )
        valid = [n for n in nums if nutrient_value_allowed(nutrient, n)]

        if valid:
            result[nutrient] = {
                "value": valid[0],
                "evidence": [r.text],
                "confidence": r.confidence,
                "box": r.box,
            }
            continue

        # Find a numeric value on the same visual row.
        row = rows[r.row_id] if 0 <= r.row_id < len(rows) else []
        candidates = []
        for c in row:
            if c.index == r.index:
                continue
            if detect_field(c.text) is not None or detect_section(c.text) is not None:
                continue
            if not nutrient_value_allowed(nutrient, c.text):
                continue
            gap = abs(c.cx - r.cx)
            if gap > 350:
                continue
            candidates.append((gap, c))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            c = candidates[0][1]
            vals = re.findall(
                r"\b\d+(?:\.\d+)?\s*(?:mg|g|kg|ml|kcal|kj|%)\b",
                c.text,
                re.I,
            )
            if vals:
                result[nutrient] = {
                    "value": vals[0],
                    "evidence": [r.text, c.text],
                    "confidence": c.confidence,
                    "box": c.box,
                }

    return result


# ============================================================
# CONTACT EXTRACTION
# ============================================================

def extract_contacts(regions):
    emails, websites, phones = [], [], []

    for r in regions:
        text = r.text
        for x in re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I):
            if x not in emails:
                emails.append(x)
        for x in re.findall(r"(?:https?://|www\.)[^\s,;]+", text, re.I):
            x = x.rstrip(".,;)")
            if x not in websites:
                websites.append(x)
        # Only identify plausible Indian contact numbers.
        for x in re.findall(r"\+91[\s-]?\d{2,5}[\s-]\d{5,8}", text):
            if x not in phones:
                phones.append(x)
        for x in re.findall(r"(?<!\d)[6-9]\d{9}(?!\d)", text):
            if x not in phones:
                phones.append(x)

    return {
        "phones": phones,
        "emails": emails,
        "websites": websites,
    }


# ============================================================
# ARRANGE
# ============================================================

def arrange(ocr_data):
    regions = make_regions(ocr_data)
    rows = build_rows(regions)

    product_information = extract_product_fields(regions, rows)
    sections = extract_sections(regions, rows)
    nutrition = extract_nutrition(regions, rows)
    contacts = extract_contacts(regions)

    return {
        "success": True,
        "source_image": ocr_data.get("image"),
        "product_information": product_information,
        "sections": sections,
        "nutrition": nutrition,
        "contacts": contacts,
        "layout": {
            "ocr_regions": len(regions),
            "visual_rows": len(rows),
        },
        "raw_ocr": ocr_data.get("regions", []),
    }


# ============================================================
# OCR
# ============================================================

class ProductReader:
    def __init__(self):
        print("=" * 70)
        print("INITIALIZING GENERAL FOOD LABEL READER")
        print("=" * 70)
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
            print("ERROR: Could not initialize PaddleOCR.")
            print(str(exc))
            sys.exit(1)

        print("OCR model loaded successfully.")
        print()

    def read_ocr(self, image_path: str) -> dict:
        if not os.path.isfile(image_path):
            raise FileNotFoundError(image_path)

        print("=" * 70)
        print("READING IMAGE")
        print("=" * 70)
        print("Image:", image_path)
        print()

        results = self.ocr.predict(image_path)
        regions = []

        for result in results:
            try:
                data = result["res"]
            except Exception:
                data = result

            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            boxes = data.get("rec_boxes", [])

            for i, text in enumerate(texts):
                text = normalize_text(text)
                if not text:
                    continue

                confidence = None
                if i < len(scores):
                    confidence = safe_float(scores[i])

                box = None
                if i < len(boxes):
                    raw_box = boxes[i]
                    if hasattr(raw_box, "tolist"):
                        box = raw_box.tolist()
                    else:
                        box = raw_box

                regions.append({
                    "text": text,
                    "confidence": confidence,
                    "box": box,
                })

        return {
            "success": True,
            "image": os.path.abspath(image_path),
            "regions": regions,
            "full_text": "\n".join(r["text"] for r in regions),
        }


# ============================================================
# DISPLAY
# ============================================================

def display_result(result):
    print()
    print("=" * 70)
    print("ARRANGED PRODUCT INFORMATION")
    print("=" * 70)

    fields = result["product_information"]
    for name, data in fields.items():
        if name == "fssai_license":
            print("fssai_license             :", data.get("values", []))
        else:
            print(f"{name:25} : {data.get('value')}")
            if data.get("additional_values"):
                print(" " * 27 + "Additional:", data["additional_values"])

    print()
    print("=" * 70)
    print("SECTIONS")
    print("=" * 70)
    if not result["sections"]:
        print("No sections detected.")
    else:
        for name, data in result["sections"].items():
            print(f"\n[{name.upper()}]")
            for line in data["content"]:
                print("  " + line)

    print()
    print("=" * 70)
    print("NUTRITION")
    print("=" * 70)
    if not result["nutrition"]:
        print("No nutrition data detected.")
    else:
        for name, data in result["nutrition"].items():
            print(f"{name:25} : {data['value']}")

    print()
    print("=" * 70)
    print("CONTACT INFORMATION")
    print("=" * 70)
    print("Phones   :", result["contacts"]["phones"])
    print("Emails   :", result["contacts"]["emails"])
    print("Websites :", result["contacts"]["websites"])


# ============================================================
# FILE PICKER / MAIN
# ============================================================

def select_image():
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title="Select Product Image",
        filetypes=[
            ("Image files", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()
    return path


def main():
    print()
    print("=" * 70)
    print("GENERAL FOOD LABEL READER V4")
    print("OCR + SPATIAL ARRANGER")
    print("=" * 70)
    print()

    image_path = select_image()

    if not image_path:
        print("No image selected.")
        return

    reader = ProductReader()

    try:
        ocr_result = reader.read_ocr(image_path)

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(project_root, "output")
        os.makedirs(output_dir, exist_ok=True)

        raw_file = os.path.join(output_dir, "ocr_result.json")
        final_file = os.path.join(output_dir, "product_result.json")

        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(ocr_result, f, indent=2, ensure_ascii=False)

        print("OCR regions:", len(ocr_result["regions"]))
        print()
        print("Arranging information using local spatial relationships...")

        arranged = arrange(ocr_result)

        with open(final_file, "w", encoding="utf-8") as f:
            json.dump(arranged, f, indent=2, ensure_ascii=False)

        print()
        print("=" * 70)
        print("COMPLETE")
        print("=" * 70)
        print("Raw OCR     :", raw_file)
        print("Final result:", final_file)
        print()

        display_result(arranged)

    except Exception as exc:
        print()
        print("=" * 70)
        print("READER FAILED")
        print("=" * 70)
        print(str(exc))
        print()
        raise


if __name__ == "__main__":
    main()
