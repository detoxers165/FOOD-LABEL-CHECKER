#!/usr/bin/env python3
# ============================================================
# GENERAL PRODUCT / FOOD LABEL READER  -  V5
# ============================================================
# Image -> preprocess -> adaptive multi-pass OCR -> merge ->
# scale-invariant spatial arranger -> structured JSON
#
# Main changes vs V4:
#   1. Real image preprocessing (EXIF, deskew, upscale, CLAHE).
#   2. Adaptive multi-pass OCR: only escalates when pass 1 is weak.
#   3. Auto rotation detection (0/90/180/270).
#   4. Optional tiling for dense small print on high-res photos.
#   5. Version-agnostic PaddleOCR wrapper (3.x predict + 2.x ocr),
#      with rec_boxes / rec_polys / dt_polys fallbacks.
#   6. All spatial thresholds expressed in "text heights", not pixels.
#   7. Fuzzy, OCR-error-tolerant label matching, anywhere in the line.
#   8. Column-aware nutrition table parsing.
#   9. CLI (single file / folder / batch) + debug overlay image.
# ============================================================

from __future__ import annotations
from regulation.label_pipeline import check_ocr_result

import argparse
import glob
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
FSSAI_RULES_FILE = os.path.join(
    os.path.dirname(__file__),
    "regulation",
    "rules.json",
)
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("GLOG_minloglevel", "2")

try:
    import cv2
    import numpy as np
except Exception as exc:  # pragma: no cover
    print("ERROR: OpenCV / NumPy are required.  pip install opencv-python numpy")
    print(str(exc))
    sys.exit(1)


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class Config:
    lang: str = "en"
    # Detection input size. PaddleOCR's default of 960 is the single biggest
    # cause of missed small print on phone photos of labels.
    det_side_len: int = 1536
    rec_score_thresh: float = 0.30
    min_confidence: float = 0.45          # regions below this are dropped
    max_side: int = 3200                  # cap for memory / speed
    min_side: int = 1400                  # upscale small crops to at least this
    auto_rotate: bool = True
    deskew: bool = True
    tile: str = "auto"                    # auto | on | off
    doc_unwarping: bool = False           # helps curved packets, costs time
    accurate: bool = False                # use server-grade det/rec models
    debug: bool = False


FIELD_ALIASES = {
    "net_quantity": [
        "net quantity", "net qty", "net weight", "net wt",
        "net content", "net contents", "quantity", "nett weight",
    ],
    "mrp": [
        "maximum retail price", "max retail price",
        "maximum retail selling price", "mrp", "m r p", "retail price",
    ],
    "batch_number": [
        "batch number", "batch no", "batch code", "batch",
        "lot number", "lot no", "lot code", "b no", "b. no", "bn",
    ],
    "manufacturing_date": [
        "date of manufacture", "manufacturing date", "manufactured date",
        "mfg date", "date of mfg", "mfd on", "packed on", "packing date",
        "date of packing", "mfg", "mfd",
    ],
    "expiry_date": [
        "expiry date", "expiration date", "exp date", "use by",
        "use before", "best before", "best before end", "exp",
    ],
    "fssai_license": [
        "fssai license", "fssai licence", "fssai lic no", "fssai",
        "licence no", "license no", "lic no",
    ],
    "manufacturer": [
        "manufactured by", "manufactured for", "manufacturer",
        "mfd by", "mfg by", "packed by",
    ],
    "marketed_by": ["marketed by", "marketed for", "marketer"],
    "customer_care": [
        "customer care", "consumer care", "customer service",
        "consumer service", "contact us", "helpline", "help line",
        "customer care details", "for queries",
    ],
    "country_of_origin": ["country of origin", "origin", "made in"],
}

# A field hit is discarded if its region also matches one of these.
# "UNIT SALE PRICE: Rs.0.35 PER g" was being returned as the MRP.
NEGATIVE_ALIASES = {
    "mrp": ["unit sale price", "unit price", "usp", "per g", "per gm", "per ml"],
    "net_quantity": ["serve size", "serving size", "per pack"],
    "batch_number": ["lic no", "licence no", "license no", "fssai"],
    "marketed_by": ["serve size", "serving size"],
}

# Labels that carry TWO fields on one line, e.g. "MFD & USE BY: 07/08/26 & 06/12/26"
COMPOUND_PATTERNS = [
    (r"mfd\s*&\s*use\s*by", ["manufacturing_date", "expiry_date"], r"&"),
    (r"mfg\s*&\s*exp", ["manufacturing_date", "expiry_date"], r"&"),
    (r"mfd\s*/\s*exp", ["manufacturing_date", "expiry_date"], r"/"),
    (r"no\.?\s*of\s*serves.*?b\.?\s*no", ["serves_per_pack", "batch_number"], r"/"),
]

SECTION_ALIASES = {
    "ingredients": ["ingredients", "ingredient", "ingredients list"],
    "allergen": ["allergen advice", "allergen information", "allergens",
                 "contains", "may contain"],
    "storage": ["storage instructions", "storage conditions", "storage",
                "store in", "how to store"],
    "usage": ["directions for use", "how to use", "usage instructions"],
    "nutrition": ["nutrition facts", "nutrition information",
                  "nutritional information", "nutritional facts",
                  "nutrition value", "nutritional value"],
}

# Canonical nutrient -> aliases (fuzzy matched)
NUTRIENTS = {
    "energy": ["energy", "calories", "energy value"],
    "protein": ["protein", "total protein", "proteins"],
    "carbohydrate": ["carbohydrate", "carbohydrates", "total carbohydrate",
                     "carbohydrates total"],
    "total_sugars": ["sugars", "total sugars", "of which sugars"],
    "added_sugars": ["added sugars", "added sugar"],
    "total_fat": ["fat", "total fat", "fats"],
    "saturated_fat": ["saturated fat", "saturates", "saturated fatty acids"],
    "trans_fat": ["trans fat", "trans fatty acids", "trans fats"],
    "dietary_fibre": ["dietary fibre", "dietary fiber", "fibre", "fiber",
                      "crude fibre"],
    "sodium": ["sodium"],
    "salt": ["salt"],
    "cholesterol": ["cholesterol"],
    "calcium": ["calcium"],
    "iron": ["iron"],
    "potassium": ["potassium"],
}

UNIT_BY_NUTRIENT = {
    "energy": r"(?:kcal|kj|cal)",
    "sodium": r"(?:mg|g)", "calcium": r"(?:mg|g|mcg|ug)",
    "iron": r"(?:mg|g|mcg|ug)", "potassium": r"(?:mg|g)",
    "cholesterol": r"(?:mg|g)",
}
DEFAULT_NUTRIENT_UNIT = r"(?:mg|g|kg|mcg|ug)"

BAD_VALUE_WORDS = {
    "advice", "information", "facts", "instructions", "conditions",
    "none", "n/a", "na", "unknown", "details", "value", "values",
}

# Characters OCR routinely swaps. Used only for *matching*, never for output.
# Folded on BOTH the text and the alias, so "lNGREDlENTS" == "INGREDIENTS".
CONFUSIONS = str.maketrans({
    "0": "o", "O": "o",
    "1": "i", "l": "i", "I": "i", "|": "i", "!": "i",
    "3": "e", "4": "a", "@": "a",
    "5": "s", "$": "s",
    "6": "g", "9": "g",
    "8": "b", "2": "z",
})

FUZZY_THRESHOLD = 0.84


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(text) -> str:
    text = str(text)
    text = (text.replace("\u2013", "-").replace("\u2014", "-")
                .replace("\u2212", "-").replace("\uff1a", ":")
                .replace("\u2019", "'").replace("\u201c", '"')
                .replace("\u201d", '"').replace("\u00a0", " "))
    return re.sub(r"\s+", " ", text).strip()


def match_key(text: str) -> str:
    """Lowercase, strip punctuation, fold common OCR confusions."""
    t = normalize_text(text).lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_text(text).lower()).translate(CONFUSIONS)


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _tokens_with_spans(text: str):
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def find_alias(text: str, aliases, threshold: float = FUZZY_THRESHOLD):
    """
    Fuzzy-find the best alias ANYWHERE in `text`.
    Returns (score, alias, char_start, char_end) or None.

    V4 only matched aliases at the start of a region, so a merged OCR line
    like "Net Qty 100g  MRP Rs.45" lost the MRP entirely.
    """
    text = normalize_text(text)
    toks = _tokens_with_spans(text)
    if not toks:
        return None

    best = None
    for alias in aliases:
        akey = compact(alias)
        if len(akey) < 2:
            continue
        n_words = max(1, len(alias.split()))
        for width in {n_words, n_words + 1}:
            for i in range(0, max(1, len(toks) - width + 1)):
                window = toks[i:i + width]
                if not window:
                    continue
                wkey = compact("".join(t[0] for t in window))
                if not wkey:
                    continue
                # Length guard stops "mrp" matching a 40-char sentence.
                if abs(len(wkey) - len(akey)) > max(3, len(akey) * 0.6):
                    continue
                score = similarity(wkey, akey)
                # Short aliases must be near-exact (avoids "exp" ~ "esp").
                need = threshold if len(akey) > 4 else 0.95
                if score < need:
                    continue
                cand = (score, len(akey), alias, window[0][1], window[-1][2])
                if best is None or (cand[0], cand[1]) > (best[0], best[1]):
                    best = cand
    if best is None:
        return None
    return best[0], best[2], best[3], best[4]


def detect_labels(text: str, alias_map: dict):
    """All label hits in a line, left to right, de-overlapped."""
    hits = []
    for key, aliases in alias_map.items():
        found = find_alias(text, aliases)
        if found:
            score, alias, s, e = found
            hits.append({"key": key, "score": score, "alias": alias,
                         "start": s, "end": e})
    hits.sort(key=lambda h: (h["start"], -h["score"]))
    out = []
    for h in hits:
        if out and h["start"] < out[-1]["end"]:
            if h["score"] > out[-1]["score"]:
                out[-1] = h
            continue
        out.append(h)
    return out


def detect_field(text: str):
    hits = detect_labels(text, FIELD_ALIASES)
    return hits[0]["key"] if hits else None


def detect_section(text: str):
    hits = detect_labels(text, SECTION_ALIASES)
    return hits[0]["key"] if hits else None


def detect_nutrient(text: str):
    hits = detect_labels(text, NUTRIENTS)
    if not hits:
        return None
    # Prefer the longest/most specific alias ("saturated fat" over "fat").
    hits.sort(key=lambda h: (len(h["alias"]), h["score"]), reverse=True)
    return hits[0]["key"]


def fix_numeric_ocr(s: str) -> str:
    """O->0 / l->1 / S->5 inside otherwise-numeric tokens only."""
    def repl(m):
        tok = m.group(0)
        if not re.search(r"\d", tok):
            return tok
        return (tok.replace("O", "0").replace("o", "0")
                   .replace("l", "1").replace("I", "1")
                   .replace("S", "5").replace("B", "8"))
    return re.sub(r"[A-Za-z0-9.,/-]+", repl, s)


# ============================================================
# PATTERNS
# ============================================================

MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"

DATE_PATTERNS = [
    r"\b\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}\b",
    r"\b\d{4}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2}\b",
    rf"\b\d{{1,2}}\s*[-/ ]?\s*{MONTHS}[a-z]*\s*[-/ ]?\s*\d{{2,4}}\b",
    rf"\b{MONTHS}[a-z]*\s*[-/ ]?\s*\d{{2,4}}\b",
    r"\b\d{1,2}\s*[./-]\s*\d{2,4}\b",           # MM/YYYY on many packs
]

DURATION_RE = re.compile(
    r"\b\d{1,3}\s*(?:days?|weeks?|months?|years?)\b(?:[^.]{0,40}?"
    r"(?:manufactur\w*|packag\w*|packing|mfg))?", re.I)

QTY_RE = re.compile(
    r"\b(?:\d+\s*[x\u00d7]\s*)?\d+(?:[.,]\d+)?\s*"
    r"(?:mg|gm?s?|g|kgs?|kg|ml|mls|l|ltr|lt|litres?|liters?|cl|"
    r"pcs?|pieces?|nos?|units?|tablets?|capsules?)\b", re.I)

PRICE_RE = re.compile(
    r"(?:\u20b9|rs\.?|inr|mrp)\s*:?\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?)"
    r"|(\d{1,4}(?:\.\d{1,2})?)\s*/-", re.I)

FSSAI_14 = re.compile(r"(?<!\d)\d{14}(?!\d)")
LICENSE_ANY = re.compile(r"(?<!\d)\d{8,20}(?!\d)")

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+\s?@\s?[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL_RE = re.compile(r"(?:https?://|www\.)[^\s,;)]+", re.I)
# "visit www.or..." was being emitted as the website www.or
KNOWN_TLDS = {"com","in","co","net","org","info","biz","io","gov","edu","me",
              "app","shop","store","online","site","uk","us","au","ca"}


def valid_url(u: str) -> bool:
    u = u.rstrip(".,;)").lower()
    host = re.sub(r"^https?://", "", u).split("/")[0]
    parts = host.split(".")
    if len(parts) < 2 or len(host) < 7:
        return False
    return parts[-1] in KNOWN_TLDS
PHONE_RES = [
    re.compile(r"\+91[\s-]?\d{2,5}[\s-]?\d{5,8}"),
    re.compile(r"\b1800[\s-]?\d{2,4}[\s-]?\d{3,5}\b"),
    re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)"),
]


def date_extract(text: str):
    t = fix_numeric_ocr(normalize_text(text))
    for p in DATE_PATTERNS:
        m = re.search(p, t, re.I)
        if m:
            return re.sub(r"\s+", "", m.group(0)) if "/" in m.group(0) or "." in m.group(0) else normalize_text(m.group(0))
    return None


def duration_extract(text: str):
    m = DURATION_RE.search(normalize_text(text))
    return normalize_text(m.group(0)) if m else None


def quantity_extract(text: str):
    t = fix_numeric_ocr(normalize_text(text))
    m = QTY_RE.search(t)
    return normalize_text(m.group(0)) if m else None


def price_extract(text: str, allow_bare: bool = True):
    t = normalize_text(text)
    # OCR frequently renders the rupee sign as one of these.
    t = re.sub(r"(?<![A-Za-z0-9])[\u20b9\u20a8\u0930?~](?=\s*\d)", "Rs ", t)
    m = PRICE_RE.search(t)
    if m:
        val = m.group(1) or m.group(2)
        return f"Rs {val}"
    if allow_bare:
        stripped = t.strip(" :.-")
        if re.fullmatch(r"\d{1,4}(?:\.\d{1,2})?", stripped):
            return f"Rs {stripped}"
    return None


def license_numbers(text: str):
    t = fix_numeric_ocr(text)
    fourteen = FSSAI_14.findall(t)
    if fourteen:                       # FSSAI numbers are exactly 14 digits
        return fourteen
    return LICENSE_ANY.findall(t)


def batch_extract(text: str):
    s = normalize_text(text).strip(" :.-")
    # "NO. OF SERVES PER PACK/B.NO.: 2.1/N4070826" -> N4070826
    if "/" in s:
        parts = [p.strip() for p in s.split("/") if p.strip()]
        coded = [p for p in parts
                 if re.search(r"[A-Za-z]", p) and re.search(r"\d", p)]
        if coded:
            s = max(coded, key=len)
    if not s or len(s) > 30:
        return None
    if match_key(s) in BAD_VALUE_WORDS:
        return None
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/\- ]{1,24}", s) and re.search(r"\d", s):
        return s
    return None


def meaningful_value(text: str) -> bool:
    s = normalize_text(text).strip(" :.-")
    if len(s) < 2 or match_key(s) in BAD_VALUE_WORDS:
        return False
    return bool(re.search(r"[A-Za-z0-9]", s))


def field_value_extract(fieldname: str, text: str, strict: bool = True):
    s = normalize_text(text)
    if fieldname == "net_quantity":
        return quantity_extract(s)
    if fieldname == "mrp":
        return price_extract(s, allow_bare=not strict)
    if fieldname in ("manufacturing_date", "expiry_date"):
        return date_extract(s) or (duration_extract(s) if fieldname == "expiry_date" else None)
    if fieldname == "fssai_license":
        nums = license_numbers(s)
        return nums or None
    if fieldname == "batch_number":
        return batch_extract(s)
    return s if meaningful_value(s) else None


# ============================================================
# REGIONS / GEOMETRY
# ============================================================

@dataclass
class Region:
    index: int
    text: str
    confidence: float
    poly: list
    x1: float
    y1: float
    x2: float
    y2: float
    source: str = "main"
    row_id: int = -1

    @property
    def cx(self): return (self.x1 + self.x2) / 2.0

    @property
    def cy(self): return (self.y1 + self.y2) / 2.0

    @property
    def width(self): return max(1.0, self.x2 - self.x1)

    @property
    def height(self): return max(1.0, self.y2 - self.y1)

    def to_dict(self):
        return {"text": self.text, "confidence": round(self.confidence, 4),
                "box": [round(self.x1, 1), round(self.y1, 1),
                        round(self.x2, 1), round(self.y2, 1)],
                "source": self.source}


@dataclass
class Layout:
    """Everything spatial is measured in `unit` = median text height.

    V4 hard-coded pixel gaps (250 / 180 / 220 / 350). Those are correct for
    exactly one image resolution and silently wrong for every other one.
    """
    unit: float = 20.0
    img_w: float = 1000.0
    img_h: float = 1000.0


def safe_float(v, default=0.0):
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except Exception:
        return default


def median(values, default=0.0):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return default
    n = len(vals)
    return float(vals[n // 2]) if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def poly_bounds(poly):
    if poly is None:
        return None
    try:
        arr = np.asarray(poly, dtype=float).reshape(-1, 2)
        if arr.size == 0:
            return None
        return (float(arr[:, 0].min()), float(arr[:, 1].min()),
                float(arr[:, 0].max()), float(arr[:, 1].max()))
    except Exception:
        return None


def iou(a: Region, b: Region) -> float:
    ix = min(a.x2, b.x2) - max(a.x1, b.x1)
    iy = min(a.y2, b.y2) - max(a.y1, b.y1)
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    union = a.width * a.height + b.width * b.height - inter
    return inter / union if union > 0 else 0.0


def build_rows(regions, layout: Layout):
    """Cluster into visual rows using vertical OVERLAP, not centre distance.

    Centre-distance clustering (V4) merges a tall heading with the small
    print beside it and splits a row whose glyph heights differ.
    """
    if not regions:
        return []
    ordered = sorted(regions, key=lambda r: (r.y1, r.x1))
    rows = []
    for r in ordered:
        placed = False
        for row in reversed(rows[-6:]):        # rows are y-sorted; look back a few
            ry1 = min(x.y1 for x in row)
            ry2 = max(x.y2 for x in row)
            inter = min(ry2, r.y2) - max(ry1, r.y1)
            smaller = min(ry2 - ry1, r.height)
            if smaller > 0 and inter >= 0.45 * smaller:
                row.append(r)
                placed = True
                break
        if not placed:
            rows.append([r])

    rows.sort(key=lambda row: median([x.cy for x in row]))
    for rid, row in enumerate(rows):
        row.sort(key=lambda r: r.x1)
        for r in row:
            r.row_id = rid
    return rows


# ============================================================
# IMAGE PREPROCESSING
# ============================================================

def imread_any(path: str):
    """Reads unicode paths, webp, tiff; applies EXIF orientation."""
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        try:
            from PIL import Image, ImageOps
            pil = ImageOps.exif_transpose(Image.open(path).convert("RGB"))
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception:
            return None
        return img
    try:
        from PIL import Image, ImageOps
        pil = Image.open(path)
        if dict(getattr(pil, "_getexif", lambda: {})() or {}).get(274, 1) != 1:
            pil = ImageOps.exif_transpose(pil.convert("RGB"))
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except Exception:
        pass
    return img


def resize_bounded(img, cfg: Config):
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest > cfg.max_side:
        s = cfg.max_side / longest
        return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), s
    if longest < cfg.min_side:
        s = min(3.0, cfg.min_side / longest)
        return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC), s
    return img, 1.0


def estimate_skew(img) -> float:
    """Small-angle deskew from the dominant text-line orientation."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
    dil = cv2.dilate(thr, kernel, iterations=2)
    contours, _ = cv2.findContours(dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles = []
    for c in contours:
        if cv2.contourArea(c) < 400:
            continue
        (_, _), (w, h), ang = cv2.minAreaRect(c)
        if w < h:
            ang += 90
        if -20 < ang < 20:
            angles.append(ang)
    if len(angles) < 5:
        return 0.0
    ang = median(angles, 0.0)
    return ang if abs(ang) > 0.4 else 0.0


def rotate_bound(img, angle: float):
    h, w = img.shape[:2]
    c = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(c, angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += nw / 2 - c[0]
    M[1, 2] += nh / 2 - c[1]
    return cv2.warpAffine(img, M, (nw, nh), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def enhance(img):
    """CLAHE on L channel + mild unsharp. Helps glare and dim phone shots."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(l)
    out = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    blur = cv2.GaussianBlur(out, (0, 0), 1.2)
    return cv2.addWeighted(out, 1.5, blur, -0.5, 0)


def binarize(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 60, 60)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 35, 12)
    return cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)


def prepare(img, cfg: Config):
    img, scale = resize_bounded(img, cfg)
    angle = estimate_skew(img) if cfg.deskew else 0.0
    if angle:
        img = rotate_bound(img, angle)
    return img, {"resize_scale": round(scale, 4), "deskew_angle": round(angle, 2)}


# ============================================================
# OCR ENGINE (version agnostic)
# ============================================================

class Engine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.mode = None
        try:
            from paddleocr import PaddleOCR
        except Exception as exc:
            raise SystemExit(
                "Could not import PaddleOCR.\n"
                "  pip install 'paddlepaddle>=3.0' 'paddleocr>=3.0'\n" + str(exc))

        attempts = []
        if cfg.accurate:
            attempts.append(dict(
                lang=cfg.lang,
                text_detection_model_name="PP-OCRv5_server_det",
                text_recognition_model_name="PP-OCRv5_server_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=cfg.doc_unwarping,
                use_textline_orientation=True,
                text_det_limit_side_len=cfg.det_side_len,
                text_det_limit_type="max",
                text_rec_score_thresh=cfg.rec_score_thresh,
            ))
        attempts += [
            dict(lang=cfg.lang,
                 use_doc_orientation_classify=False,
                 use_doc_unwarping=cfg.doc_unwarping,
                 use_textline_orientation=True,
                 text_det_limit_side_len=cfg.det_side_len,
                 text_det_limit_type="max",
                 text_rec_score_thresh=cfg.rec_score_thresh),
            dict(lang=cfg.lang,
                 use_doc_orientation_classify=False,
                 use_doc_unwarping=False,
                 use_textline_orientation=True),
            dict(lang=cfg.lang, use_angle_cls=True, show_log=False),
            dict(lang=cfg.lang),
        ]

        last = None
        for kwargs in attempts:
            try:
                self.ocr = PaddleOCR(**kwargs)
                self.init_kwargs = kwargs
                break
            except Exception as exc:
                last = exc
        else:
            raise SystemExit(f"Could not initialize PaddleOCR: {last}")

        self.mode = "predict" if hasattr(self.ocr, "predict") else "ocr"

    # ---- raw call -------------------------------------------------
    def _raw(self, image):
        if self.mode == "predict":
            return self.ocr.predict(image)
        try:
            return self.ocr.ocr(image, cls=True)
        except TypeError:
            return self.ocr.ocr(image)

    # ---- result parsing -------------------------------------------
    @staticmethod
    def _parse(results):
        """Handles PaddleOCR 3.x dicts and 2.x nested lists."""
        out = []
        if results is None:
            return out

        def take_dict(d):
            texts = list(d.get("rec_texts") or [])
            scores = list(d.get("rec_scores") or [])
            # rec_boxes is empty when doc-unwarping is on -> fall back to polys.
            polys = d.get("rec_polys")
            if polys is None or len(polys) == 0:
                polys = d.get("rec_boxes")
            if polys is None or len(polys) == 0:
                polys = d.get("dt_polys")
            polys = list(polys) if polys is not None else []
            for i, t in enumerate(texts):
                sc = safe_float(scores[i], 0.0) if i < len(scores) else 0.0
                pl = polys[i] if i < len(polys) else None
                if pl is not None and hasattr(pl, "tolist"):
                    pl = pl.tolist()
                if isinstance(pl, (list, tuple)) and len(pl) == 4 and \
                        all(isinstance(v, (int, float)) for v in pl):
                    x1, y1, x2, y2 = pl
                    pl = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                out.append((t, sc, pl))

        for res in results if isinstance(results, (list, tuple)) else [results]:
            if res is None:
                continue
            d = None
            if isinstance(res, dict):
                d = res.get("res", res)
            else:
                for attr in ("json", "res"):
                    try:
                        cand = res[attr] if not isinstance(res, list) else None
                    except Exception:
                        cand = None
                    if isinstance(cand, dict):
                        d = cand.get("res", cand)
                        break
                if d is None and hasattr(res, "get"):
                    d = res
            if isinstance(d, dict) and ("rec_texts" in d or "rec_scores" in d):
                take_dict(d)
                continue
            # legacy 2.x: [[poly, (text, score)], ...]
            if isinstance(res, (list, tuple)):
                for line in res:
                    try:
                        poly, (txt, sc) = line[0], line[1]
                        out.append((txt, safe_float(sc, 0.0), poly))
                    except Exception:
                        continue
        return out

    def run(self, image, source="main", offset=(0, 0), start_index=0):
        regions = []
        parsed = self._parse(self._raw(image))
        ox, oy = offset
        for t, sc, poly in parsed:
            text = normalize_text(t)
            if not text:
                continue
            b = poly_bounds(poly)
            if b is None:
                continue
            x1, y1, x2, y2 = b
            regions.append(Region(
                index=start_index + len(regions), text=text, confidence=sc,
                poly=(np.asarray(poly, float).reshape(-1, 2) + [ox, oy]).tolist(),
                x1=x1 + ox, y1=y1 + oy, x2=x2 + ox, y2=y2 + oy, source=source))
        return regions


# ============================================================
# MULTI-PASS STRATEGY
# ============================================================

def pass_score(regions):
    """Quality proxy: confident characters recovered."""
    return sum(len(r.text) * (r.confidence ** 2) for r in regions)


def merge_regions(groups):
    """Union across passes; drop near-duplicates, keep the confident one."""
    merged = []
    for group in groups:
        for r in sorted(group, key=lambda x: -x.confidence):
            dup = False
            for m in merged:
                if iou(r, m) > 0.45:
                    a, b = compact(r.text), compact(m.text)
                    if similarity(a, b) > 0.7 or a in b or b in a:
                        if len(r.text) > len(m.text) * 1.25 and r.confidence >= m.confidence - 0.05:
                            m.text, m.confidence, m.poly = r.text, r.confidence, r.poly
                        dup = True
                        break
            if not dup:
                merged.append(r)
    merged.sort(key=lambda r: (r.y1, r.x1))
    for i, r in enumerate(merged):
        r.index = i
    return merged


def detect_rotation(engine: Engine, img):
    """Cheap 4-way orientation probe on a downscaled copy."""
    small, _ = resize_bounded(img, Config(max_side=1000, min_side=600))
    best_angle, best = 0, None
    for angle in (0, 90, 180, 270):
        probe = small if angle == 0 else rotate_bound(small, -angle)
        regs = engine.run(probe, source=f"probe{angle}")
        sc = pass_score(regs)
        if best is None or sc > best:
            best, best_angle = sc, angle
        if angle == 0 and sc > 400:      # upright and clearly readable
            return 0, sc
    return best_angle, best


def should_tile(regions, img, cfg: Config) -> bool:
    if cfg.tile == "off":
        return False
    if cfg.tile == "on":
        return True
    if not regions:
        return True
    h, w = img.shape[:2]
    med_h = median([r.height for r in regions], 20.0)
    low_conf = sum(1 for r in regions if r.confidence < 0.7) / max(1, len(regions))
    return (max(h, w) > 1600 and med_h < 0.016 * h) or low_conf > 0.35


def tiled_pass(engine: Engine, img, cols=2, rows=2, overlap=0.18):
    h, w = img.shape[:2]
    tw, th = int(w / cols), int(h / rows)
    ox, oy = int(tw * overlap), int(th * overlap)
    out = []
    for r in range(rows):
        for c in range(cols):
            x1 = max(0, c * tw - ox)
            y1 = max(0, r * th - oy)
            x2 = min(w, (c + 1) * tw + ox)
            y2 = min(h, (r + 1) * th + oy)
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            crop = cv2.resize(crop, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
            regs = engine.run(crop, source=f"tile{r}{c}")
            for reg in regs:                      # map back to full-image coords
                reg.x1 = reg.x1 / 1.5 + x1
                reg.x2 = reg.x2 / 1.5 + x1
                reg.y1 = reg.y1 / 1.5 + y1
                reg.y2 = reg.y2 / 1.5 + y1
                reg.poly = [[p[0] / 1.5 + x1, p[1] / 1.5 + y1] for p in reg.poly]
            out.extend(regs)
    return out


def read_image(engine: Engine, path: str, cfg: Config):
    raw = imread_any(path)
    if raw is None:
        raise ValueError(f"Could not decode image: {path}")

    meta = {"original_size": [raw.shape[1], raw.shape[0]], "passes": []}

    if cfg.auto_rotate:
        angle, _ = detect_rotation(engine, raw)
        if angle:
            raw = rotate_bound(raw, -angle)
        meta["rotation_applied"] = angle

    base, prep_meta = prepare(raw, cfg)
    meta.update(prep_meta)

    groups = []
    primary = engine.run(base, source="base")
    groups.append(primary)
    meta["passes"].append({"name": "base", "regions": len(primary),
                           "score": round(pass_score(primary), 1)})

    strong = (len(primary) >= 12 and
              median([r.confidence for r in primary], 0) > 0.88)

    if not strong:
        enhanced = engine.run(enhance(base), source="enhanced")
        groups.append(enhanced)
        meta["passes"].append({"name": "enhanced", "regions": len(enhanced),
                               "score": round(pass_score(enhanced), 1)})
        if pass_score(enhanced) < pass_score(primary) * 0.8 or len(primary) < 8:
            bw = engine.run(binarize(base), source="binary")
            groups.append(bw)
            meta["passes"].append({"name": "binary", "regions": len(bw),
                                   "score": round(pass_score(bw), 1)})

    if should_tile(primary, base, cfg):
        tiles = tiled_pass(engine, enhance(base))
        groups.append(tiles)
        meta["passes"].append({"name": "tiled", "regions": len(tiles),
                               "score": round(pass_score(tiles), 1)})

    regions = merge_regions(groups)
    regions = [r for r in regions if r.confidence >= cfg.min_confidence]
    for i, r in enumerate(regions):
        r.index = i

    layout = Layout(unit=max(8.0, median([r.height for r in regions], 20.0)),
                    img_w=base.shape[1], img_h=base.shape[0])
    meta["median_text_height"] = round(layout.unit, 1)
    return regions, layout, base, meta


# ============================================================
# SPATIAL SCORING (scale invariant)
# ============================================================

def same_row_score(label: Region, cand: Region, fieldname: str, L: Layout):
    u = L.unit
    y_gap = abs(cand.cy - label.cy)
    if y_gap > max(label.height, cand.height) * 0.9:
        return -1
    if cand.x1 >= label.x2:
        gap = cand.x1 - label.x2
        if gap > 14 * u:
            return -1
        base, penalty = 1000.0, gap / u * 22.0
    else:
        gap = label.x1 - cand.x2
        if gap > 8 * u:
            return -1
        base, penalty = 450.0, gap / u * 30.0
    if field_value_extract(fieldname, cand.text, strict=False) is None:
        return -1
    return base - penalty - (y_gap / u) * 60.0


def below_score(label: Region, cand: Region, fieldname: str, L: Layout):
    u = L.unit
    v_gap = cand.y1 - label.y2
    if v_gap < -0.3 * u or v_gap > 6 * u:
        return -1
    h_gap = abs(cand.cx - label.cx)
    if h_gap > max(9 * u, label.width * 1.2):
        return -1
    if field_value_extract(fieldname, cand.text, strict=False) is None:
        return -1
    return 700.0 - (v_gap / u) * 45.0 - (h_gap / u) * 25.0


def find_spatial_value(label: Region, fieldname: str, rows, used, L: Layout):
    row = rows[label.row_id] if 0 <= label.row_id < len(rows) else []
    cands = []
    for c in row:
        if c.index == label.index or c.index in used:
            continue
        if detect_field(c.text) is not None or blocked(fieldname, c.text):
            continue
        s = same_row_score(label, c, fieldname, L)
        if s > 0:
            cands.append((s, c))
    if cands:
        return max(cands, key=lambda x: x[0])

    for rid in range(label.row_id + 1, min(len(rows), label.row_id + 4)):
        rc = []
        for c in rows[rid]:
            if c.index in used or detect_field(c.text) is not None \
                    or blocked(fieldname, c.text):
                continue
            s = below_score(label, c, fieldname, L)
            if s > 0:
                rc.append((s, c))
        if rc:
            return max(rc, key=lambda x: x[0])
    return None


# ============================================================
# FIELD EXTRACTION
# ============================================================

def inline_value(fieldname: str, region_text: str, hits):
    """Text between this label and the next label on the same line."""
    me = next((h for h in hits if h["key"] == fieldname), None)
    if me is None:
        return None
    later = [h["start"] for h in hits if h["start"] > me["end"]]
    end = min(later) if later else len(region_text)
    rest = region_text[me["end"]:end].strip(" :=-.\u2013")
    if not rest:
        return None
    return field_value_extract(fieldname, rest, strict=False)


def blocked(fieldname: str, text: str) -> bool:
    """True if this region must not supply a value for this field."""
    for neg in NEGATIVE_ALIASES.get(fieldname, []):
        if find_alias(text, [neg]):
            return True
    return False


def compound_split(r: Region, rows=None, L: Layout = None):
    """Yield (field, value) pairs for 'MFD & USE BY: 07/08/26 & 06/12/26'.

    The value often lands in a SEPARATE OCR region from the label, so when the
    label region has no usable tail we look right/below for the value cell.
    """
    key = re.sub(r"\s+", " ",
                 re.sub(r"[^a-z0-9&/ ]+", " ", normalize_text(r.text).lower())).strip()
    for pat, fieldnames, sep in COMPOUND_PATTERNS:
        m = re.search(pat, key)
        if not m:
            continue
        tail = r.text[int(len(r.text) * m.end() / max(1, len(key))):]
        tail = tail.strip(" :=-")
        parts = [p.strip() for p in re.split(sep, tail) if p.strip()]

        if len(parts) < 2 and rows is not None and L is not None:
            tol = L.unit * 1.6
            best = None
            for row in rows:
                for c in row:
                    if c.index == r.index or abs(c.cy - r.cy) > tol:
                        continue
                    if c.x1 < r.x2 - L.unit:
                        continue
                    if not re.search(sep, c.text):
                        continue
                    d = c.x1 - r.x2
                    if best is None or d < best[0]:
                        best = (d, c)
            if best:
                parts = [p.strip() for p in re.split(sep, best[1].text) if p.strip()]

        if len(parts) < 2:
            continue
        out = []
        for fieldname, part in zip(fieldnames, parts):
            if fieldname == "serves_per_pack":
                continue
            val = field_value_extract(fieldname, part, strict=False)
            if val:
                out.append((fieldname, val))
        if out:
            return out
    return []


def extract_product_fields(regions, rows, L: Layout):
    fields = {}
    used = set()

    for r in regions:
        for fieldname, val in compound_split(r, rows, L):
            fields.setdefault(fieldname, {
                "value": val, "label": r.text, "match_score": 1.0,
                "label_confidence": round(r.confidence, 3),
                "label_box": [r.x1, r.y1, r.x2, r.y2],
                "evidence": [r.text], "source": "compound"})

        hits = detect_labels(r.text, FIELD_ALIASES)
        for hit in hits:
            fieldname = hit["key"]
            if fieldname == "fssai_license" or fieldname in fields and \
                    fields[fieldname].get("source") == "compound":
                continue
            if blocked(fieldname, r.text):
                continue

            value = inline_value(fieldname, r.text, hits)
            value_region = r if value is not None else None

            if value is None:
                found = find_spatial_value(r, fieldname, rows, used, L)
                if found:
                    _, cand = found
                    value = field_value_extract(fieldname, cand.text, strict=False)
                    if value is not None:
                        value_region = cand
                        used.add(cand.index)

            entry = {"value": value, "label": r.text,
                     "match_score": round(hit["score"], 3),
                     "label_confidence": round(r.confidence, 3),
                     "label_box": [r.x1, r.y1, r.x2, r.y2],
                     "evidence": [r.text]}
            if value_region is not None and value_region.index != r.index:
                entry["value_confidence"] = round(value_region.confidence, 3)
                entry["value_box"] = [value_region.x1, value_region.y1,
                                      value_region.x2, value_region.y2]
                entry["evidence"].append(value_region.text)

            if fieldname not in fields:
                fields[fieldname] = entry
            else:
                cur = fields[fieldname]
                if cur.get("value") is None and value is not None:
                    fields[fieldname] = entry
                elif value is not None and value != cur.get("value"):
                    cur.setdefault("additional_values", [])
                    for v in (value if isinstance(value, list) else [value]):
                        if v not in cur["additional_values"]:
                            cur["additional_values"].append(v)
                            cur["evidence"].append(r.text)

    fssai = collect_fssai(regions, rows, L)
    if fssai:
        fields["fssai_license"] = {"values": [x["value"] for x in fssai],
                                   "evidence": fssai}
    elif any(find_alias(r.text, FIELD_ALIASES["fssai_license"]) for r in regions):
        fields["fssai_license"] = {"values": [], "evidence": []}
    return fields


def collect_fssai(regions, rows, L: Layout):
    entries, seen = [], set()
    for r in regions:
        if not find_alias(r.text, FIELD_ALIASES["fssai_license"]):
            continue
        for n in license_numbers(r.text):
            if n not in seen:
                seen.add(n)
                entries.append({"value": n, "evidence": [r.text],
                                "confidence": round(r.confidence, 3)})
        nearby = list(rows[r.row_id]) if 0 <= r.row_id < len(rows) else []
        for extra in (r.row_id + 1, r.row_id + 2):
            if extra < len(rows):
                nearby += rows[extra]
        for c in nearby:
            if c.index == r.index or len(c.text) > 40:
                continue
            if abs(c.cx - r.cx) > 12 * L.unit:
                continue
            for n in license_numbers(c.text):
                if n not in seen:
                    seen.add(n)
                    entries.append({"value": n, "evidence": [r.text, c.text],
                                    "confidence": round(c.confidence, 3)})
    # 14-digit hits first
    entries.sort(key=lambda e: (len(e["value"]) != 14,))
    return entries


# ============================================================
# SECTIONS
# ============================================================

def extract_sections(regions, rows, L: Layout):
    sections = {}
    for r in regions:
        hits = detect_labels(r.text, SECTION_ALIASES)
        if not hits:
            continue
        name = hits[0]["key"]
        if name in sections:
            continue

        content = []
        tail = r.text[hits[0]["end"]:].strip(" :=-.\u2013")
        if tail and len(tail) > 2:
            content.append(tail)

        block_left, block_right = r.x1, max(r.x2, r.x1 + 6 * L.unit)
        for rid in range(r.row_id + 1, min(len(rows), r.row_id + 10)):
            row = rows[rid]
            if any(detect_section(c.text) for c in row):
                break
            gap = min(c.y1 for c in row) - max(
                x.y2 for x in rows[rid - 1]) if rid - 1 >= 0 else 0
            if gap > 2.2 * L.unit:        # a real visual break ends the block
                break
            picked = []
            for c in row:
                if detect_field(c.text) is not None:
                    continue
                overlap = min(block_right, c.x2) - max(block_left, c.x1)
                if overlap > -1.5 * L.unit:
                    picked.append(c)
            if not picked:
                break
            content.extend(c.text for c in picked)
            block_left = min(block_left, min(c.x1 for c in picked))
            block_right = max(block_right, max(c.x2 for c in picked))

        cleaned = []
        for item in content:
            item = normalize_text(item)
            if item and item not in cleaned:
                cleaned.append(item)
        if cleaned:
            sections[name] = {"heading": r.text, "content": cleaned,
                              "text": " ".join(cleaned),
                              "confidence": round(r.confidence, 3)}
    return sections


# ============================================================
# NUTRITION (column aware)
# ============================================================

# Order matters: "% RDA Per Serve" contains "per serve", so RDA is tested first.
COLUMN_HINTS = [
    ("rda", [r"%\s*rda", r"\brda\b", r"%\s*dv", r"daily\s*value"]),
    ("per_100ml", [r"per\s*100\s*ml", r"\b100\s*ml\b", r"per\s*100\s*millilit\w*"]),
    ("per_100g", [r"per\s*100\s*g\b", r"\b100\s*g\b", r"per\s*100\s*gram\w*"]),
    ("per_serving", [r"per\s*serv\w*", r"per\s*portion"]),
]

# Spanning titles that sit ABOVE the real header row. Using "Serve Size 20g**"
# as a column anchor is what shifted every value one column to the right.
SPAN_HEADERS = [r"serve\s*size", r"serving\s*size", r"nutrition\s*information",
                r"nutritional\s*information", r"approximate\s*value"]


def is_span_header(text: str) -> bool:
    k = match_key(text)
    return any(re.search(p, k) for p in SPAN_HEADERS)


def find_columns(regions, rows, L: Layout):
    """Pick the row that declares the most distinct value columns."""
    best, best_row = {}, -1
    for row in rows:
        found = {}
        for c in row:
            if is_span_header(c.text):
                continue
            k = match_key(c.text)
            for name, pats in COLUMN_HINTS:
                if name in found:
                    continue
                if any(re.search(p, k) for p in pats):
                    found[name] = c.cx
                    break
        if len(found) > len(best):
            best, best_row = found, row[0].row_id
    return (best, best_row) if len(best) >= 1 else ({}, -1)


def value_tokens(text: str, nutrient: str):
    """Keep the unit attached - a bare '6' is useless and dangerous."""
    unit = UNIT_BY_NUTRIENT.get(nutrient, DEFAULT_NUTRIENT_UNIT)
    t = fix_numeric_ocr(normalize_text(text))
    out = []
    for m in re.finditer(rf"(\d+(?:[.,]\d+)?)\s*({unit}|%)?", t, re.I):
        if not m.group(1):
            continue
        tok = m.group(0).strip()
        if tok:
            out.append(normalize_text(tok))
    return out


def has_unit(tok: str, nutrient: str) -> bool:
    unit = UNIT_BY_NUTRIENT.get(nutrient, DEFAULT_NUTRIENT_UNIT)
    return bool(re.search(rf"\d\s*{unit}\b", tok, re.I))


def is_percent(tok: str) -> bool:
    return "%" in tok


def extract_nutrition(regions, rows, L: Layout):
    """Row-pitch constrained table reader.

    The old version took the nearest numeric token to each nutrient label.
    In a tightly-packed table (12px row pitch, 9px glyphs) the nearest token
    is frequently the NEXT row's value, which is why energy returned protein's
    number. Values must now sit within a fraction of the measured row pitch.
    """
    result = {}
    columns, header_row = find_columns(regions, rows, L)

    heading_rows = [r.row_id for r in regions if detect_section(r.text) == "nutrition"]
    table_start = min(heading_rows) if heading_rows else header_row

    # Collect the nutrient label cells that belong to the table.
    labels = []
    for r in regions:
        hits = detect_labels(r.text, NUTRIENTS)
        if not hits:
            continue
        hits.sort(key=lambda h: (len(h["alias"]), h["score"]), reverse=True)
        hit = hits[0]
        if hit["start"] > 2 and len(r.text) > 30:
            continue
        if table_start >= 0 and r.row_id < table_start:
            continue
        labels.append((r, hit))

    if not labels:
        return result

    # Measure the row pitch from the label column itself.
    ys = sorted(r.cy for r, _ in labels)
    gaps = [b - a for a, b in zip(ys, ys[1:]) if b - a > 1]
    pitch = median(gaps, L.unit * 1.4) or L.unit * 1.4
    y_tol = max(L.unit * 0.55, pitch * 0.42)

    label_xs = [r.x2 for r, _ in labels]
    value_zone_left = median(label_xs, 0.0)

    for r, hit in labels:
        nutrient = hit["key"]
        cells = []

        tail = r.text[hit["end"]:]
        if tail.strip():
            span = max(1.0, r.width * (len(tail) / max(1, len(r.text))))
            for tok in value_tokens(tail, nutrient):
                cells.append((r.x2 - span / 2, tok))

        for c in regions:
            if c.index == r.index:
                continue
            if abs(c.cy - r.cy) > y_tol:          # <-- the off-by-one fix
                continue
            if c.x1 < min(r.x2, value_zone_left) - L.unit:
                continue
            if detect_nutrient(c.text) is not None or is_span_header(c.text):
                continue
            for tok in value_tokens(c.text, nutrient):
                cells.append((c.cx, tok))

        if not cells:
            continue
        cells.sort(key=lambda x: x[0])

        entry = {"evidence": [r.text], "confidence": round(r.confidence, 3)}

        if columns:
            assigned = {}
            anchors = sorted(columns.items(), key=lambda kv: kv[1])
            spacing = min((b[1] - a[1] for a, b in zip(anchors, anchors[1:])),
                          default=6 * L.unit)
            for name, cx in anchors:
                best_tok, best_d = None, None
                for tcx, tok in cells:
                    d = abs(tcx - cx)
                    if d > max(3 * L.unit, spacing * 0.6):
                        continue
                    # A gram column must not receive a percentage, and vice versa.
                    if name == "rda" and not is_percent(tok):
                        continue
                    if name != "rda" and is_percent(tok):
                        continue
                    if best_d is None or d < best_d:
                        best_tok, best_d = tok, d
                if best_tok is not None:
                    assigned[name] = best_tok
            if assigned:
                entry["values"] = assigned
                entry["value"] = (assigned.get("per_100g")
                                  or assigned.get("per_100ml")
                                  or next(iter(assigned.values())))
                entry["basis"] = ("per_100ml" if "per_100ml" in assigned
                                  else "per_100g" if "per_100g" in assigned else None)
                result[nutrient] = entry
                continue

        unit_cells = [t for _, t in cells if has_unit(t, nutrient)]
        if unit_cells:
            entry["value"] = unit_cells[0]
        else:
            entry["value"] = cells[0][1]
            entry["unit_missing"] = True
        entry["all_values"] = [t for _, t in cells][:4]
        result[nutrient] = entry
    return result


# ============================================================
# CONTACTS
# ============================================================

def extract_contacts(regions):
    emails, websites, phones = [], [], []
    for r in regions:
        t = r.text
        for x in EMAIL_RE.findall(t):
            x = x.replace(" ", "")
            if x not in emails:
                emails.append(x)
        for x in URL_RE.findall(t):
            x = x.rstrip(".,;)")
            if not valid_url(x):
                continue
            if x not in websites:
                websites.append(x)
        digits = fix_numeric_ocr(t)
        for rx in PHONE_RES:
            for x in rx.findall(digits):
                x = normalize_text(x)
                if x not in phones:
                    phones.append(x)
    return {"phones": phones, "emails": emails, "websites": websites}


# ============================================================
# ASSEMBLY
# ============================================================

def arrange(regions, layout: Layout, meta: dict, image_path: str):
    rows = build_rows(regions, layout)
    product = extract_product_fields(regions, rows, layout)
    sections = extract_sections(regions, rows, layout)
    nutrition = extract_nutrition(regions, rows, layout)
    contacts = extract_contacts(regions)

    confidences = [r.confidence for r in regions]
    filled = sum(1 for v in product.values()
                 if v.get("value") or v.get("values"))

    return {
        "success": True,
        "source_image": os.path.abspath(image_path),
        "quality": {
            "ocr_regions": len(regions),
            "visual_rows": len(rows),
            "mean_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
            "low_confidence_regions": sum(1 for c in confidences if c < 0.7),
            "fields_found": filled,
            "median_text_height_px": meta.get("median_text_height"),
            "warnings": build_warnings(regions, product, meta),
        },
        "preprocessing": meta,
        "product_information": product,
        "sections": sections,
        "nutrition": nutrition,
        "contacts": contacts,
        "full_text": "\n".join(r.text for r in regions),
        "raw_ocr": [r.to_dict() for r in regions],
    }


def build_warnings(regions, product, meta):
    w = []
    if len(regions) < 8:
        w.append("Very few text regions found - image may be blurry, "
                 "too small, or badly lit.")
    if meta.get("median_text_height", 99) < 12:
        w.append("Text is very small relative to the image; "
                 "shoot closer or use --tile on.")
    confs = [r.confidence for r in regions]
    if confs and sum(confs) / len(confs) < 0.75:
        w.append("Low mean OCR confidence - consider --accurate.")
    if not product:
        w.append("No labelled fields matched. If the label is not in English, "
                 "pass --lang (e.g. --lang devanagari).")
    return w


def draw_debug(image, regions, out_path):
    canvas = image.copy()
    for r in regions:
        color = (0, 180, 0) if r.confidence >= 0.8 else (0, 165, 255) if r.confidence >= 0.6 else (0, 0, 255)
        pts = np.asarray(r.poly, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [pts], True, color, 2)
        cv2.putText(canvas, f"{r.index}", (int(r.x1), max(12, int(r.y1) - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    cv2.imwrite(out_path, canvas)
    return out_path


# ============================================================
# MULTI-IMAGE MERGE  (front + back + nutrition panel = one product)
# ============================================================

def _field_rank(entry):
    """Higher is better: real value, confident label, confident value."""
    if not entry:
        return (-1, 0.0)
    has_value = 1 if (entry.get("value") or entry.get("values")) else 0
    conf = (safe_float(entry.get("label_confidence"), 0.0)
            + safe_float(entry.get("value_confidence"),
                         safe_float(entry.get("label_confidence"), 0.0))) / 2.0
    conf += safe_float(entry.get("match_score"), 0.0) * 0.25
    return (has_value, conf)


def _nutrient_rank(entry):
    if not entry:
        return (0, 0, 0.0)
    vals = entry.get("values") or {}
    columns = len(vals)
    united = 0 if entry.get("unit_missing") else 1
    return (columns, united, safe_float(entry.get("confidence"), 0.0))


def merge_results(results, label="merged_product"):
    """Combine several images of the SAME product into one record.

    Each field is taken from whichever image read it most confidently.
    Disagreements are preserved under 'conflicts' rather than silently
    dropped, because a wrong MRP is worse than a flagged one.
    """
    merged = {
        "success": True,
        "product": label,
        "source_images": [r.get("source_image") for r in results],
        "image_count": len(results),
        "product_information": {},
        "sections": {},
        "nutrition": {},
        "contacts": {"phones": [], "emails": [], "websites": []},
        "conflicts": {},
        "per_image": [],
    }

    # ---- product fields ----
    for res in results:
        src = os.path.basename(res.get("source_image", ""))
        for name, entry in (res.get("product_information") or {}).items():
            entry = dict(entry)
            entry["from_image"] = src
            cur = merged["product_information"].get(name)
            if name == "fssai_license":                      # union, not pick
                vals = list((cur or {}).get("values", []))
                for v in entry.get("values", []):
                    if v not in vals:
                        vals.append(v)
                ev = list((cur or {}).get("evidence", [])) + entry.get("evidence", [])
                merged["product_information"][name] = {"values": vals, "evidence": ev}
                continue
            if cur is None:
                merged["product_information"][name] = entry
                continue
            new_v, cur_v = entry.get("value"), cur.get("value")
            if new_v and cur_v and normalize_text(str(new_v)) != normalize_text(str(cur_v)):
                merged["conflicts"].setdefault(name, [])
                for cand in ({"value": cur_v, "from_image": cur.get("from_image")},
                             {"value": new_v, "from_image": src}):
                    if cand not in merged["conflicts"][name]:
                        merged["conflicts"][name].append(cand)
            if _field_rank(entry) > _field_rank(cur):
                merged["product_information"][name] = entry

    # ---- sections: keep the longest reading of each ----
    for res in results:
        src = os.path.basename(res.get("source_image", ""))
        for name, sec in (res.get("sections") or {}).items():
            sec = dict(sec); sec["from_image"] = src
            cur = merged["sections"].get(name)
            if cur is None or len(sec.get("text", "")) > len(cur.get("text", "")):
                merged["sections"][name] = sec

    # ---- nutrition: best row wins, per nutrient ----
    for res in results:
        src = os.path.basename(res.get("source_image", ""))
        for name, entry in (res.get("nutrition") or {}).items():
            entry = dict(entry); entry["from_image"] = src
            cur = merged["nutrition"].get(name)
            if cur is None or _nutrient_rank(entry) > _nutrient_rank(cur):
                merged["nutrition"][name] = entry

    # ---- contacts: union ----
    for res in results:
        for k, vals in (res.get("contacts") or {}).items():
            for v in vals:
                if v not in merged["contacts"][k]:
                    merged["contacts"][k].append(v)

    # ---- quality roll-up ----
    regions = sum(r["quality"]["ocr_regions"] for r in results)
    means = [r["quality"]["mean_confidence"] for r in results if r["quality"]["ocr_regions"]]
    warnings = []
    for r in results:
        for w in r["quality"]["warnings"]:
            if w not in warnings:
                warnings.append(w)
    filled = sum(1 for v in merged["product_information"].values()
                 if v.get("value") or v.get("values"))
    if merged["conflicts"]:
        warnings.append(f"{len(merged['conflicts'])} field(s) disagreed between "
                        f"images - see 'conflicts'.")
    merged["quality"] = {
        "images": len(results),
        "ocr_regions": regions,
        "mean_confidence": round(sum(means) / len(means), 3) if means else 0.0,
        "fields_found": filled,
        "nutrients_found": len(merged["nutrition"]),
        "warnings": warnings,
    }
    for r in results:
        merged["per_image"].append({
            "image": os.path.basename(r.get("source_image", "")),
            "regions": r["quality"]["ocr_regions"],
            "mean_confidence": r["quality"]["mean_confidence"],
            "fields_found": r["quality"]["fields_found"],
        })
    merged["full_text"] = "\n\n".join(r.get("full_text", "") for r in results)
    return merged


def display_merged(m):
    print()
    print("=" * 70)
    print(f"MERGED PRODUCT  ({m['image_count']} images)")
    print("=" * 70)
    for row in m["per_image"]:
        print(f"  {row['image'][:38]:38} regions={row['regions']:<4} "
              f"conf={row['mean_confidence']:<6} fields={row['fields_found']}")
    q = m["quality"]
    print(f"\n  total fields={q['fields_found']}  nutrients={q['nutrients_found']}  "
          f"mean_conf={q['mean_confidence']}")
    for w in q["warnings"]:
        print("  ! " + w)

    print("\n" + "=" * 70); print("PRODUCT INFORMATION"); print("=" * 70)
    for name, d in m["product_information"].items():
        val = d.get("values") if "values" in d else d.get("value")
        print(f"{name:22} : {val}   <- {d.get('from_image','')}")
    if m["conflicts"]:
        print("\n" + "=" * 70); print("CONFLICTS"); print("=" * 70)
        for name, opts in m["conflicts"].items():
            print(f"{name}:")
            for o in opts:
                print(f"    {o['value']}   ({o['from_image']})")

    print("\n" + "=" * 70); print("NUTRITION"); print("=" * 70)
    for name, d in m["nutrition"].items():
        print(f"{name:22} : {d.get('values', d.get('value'))}")

    print("\n" + "=" * 70); print("SECTIONS"); print("=" * 70)
    for name, d in m["sections"].items():
        print(f"\n[{name.upper()}]  <- {d.get('from_image','')}")
        print("  " + d["text"][:500])

    print("\n" + "=" * 70); print("CONTACTS"); print("=" * 70)
    for k, v in m["contacts"].items():
        print(f"{k:22} : {v}")


# ============================================================
# DISPLAY
# ============================================================

def display_result(result):
    q = result["quality"]
    print()
    print("=" * 70)
    print("QUALITY")
    print("=" * 70)
    print(f"regions={q['ocr_regions']}  rows={q['visual_rows']}  "
          f"mean_conf={q['mean_confidence']}  fields={q['fields_found']}")
    for warn in q["warnings"]:
        print("  ! " + warn)

    print()
    print("=" * 70)
    print("PRODUCT INFORMATION")
    print("=" * 70)
    if not result["product_information"]:
        print("  (none detected)")
    for name, data in result["product_information"].items():
        if "values" in data:
            print(f"{name:22} : {data['values']}")
        else:
            print(f"{name:22} : {data.get('value')}")
            if data.get("additional_values"):
                print(" " * 24 + "also: " + str(data["additional_values"]))

    print()
    print("=" * 70)
    print("SECTIONS")
    print("=" * 70)
    if not result["sections"]:
        print("  (none detected)")
    for name, data in result["sections"].items():
        print(f"\n[{name.upper()}]")
        print("  " + data["text"][:600])

    print()
    print("=" * 70)
    print("NUTRITION")
    print("=" * 70)
    if not result["nutrition"]:
        print("  (none detected)")
    for name, data in result["nutrition"].items():
        if "values" in data:
            print(f"{name:22} : {data['values']}")
        else:
            print(f"{name:22} : {data['value']}")

    print()
    print("=" * 70)
    print("CONTACTS")
    print("=" * 70)
    for k, v in result["contacts"].items():
        print(f"{k:22} : {v}")


# ============================================================
# CLI
# ============================================================



# ============================================================
# LEGAL METROLOGY COMPLIANCE ENGINE  (SIH 26034, stage 2/3)
# Judges the extractor's JSON output against the Legal Metrology
# (Packaged Commodities) Rules, 2011. Runs automatically after every
# extraction below - this is one tool, not two.
# ============================================================
from dataclasses import asdict

# ---- status values --------------------------------------------------------
PASS = "PASS"
FAIL = "FAIL"
REVIEW = "NEEDS_REVIEW"     # extraction may have missed it - don't accuse
NOT_APPLICABLE = "NOT_APPLICABLE"
NOT_CHECKED = "NOT_CHECKED"    # this software cannot judge this clause at all

STATUS_WEIGHT = {PASS: 1.0, FAIL: 0.0}   # only these two count toward the score


@dataclass
class Verdict:
    rule_id: str
    title: str
    clause: str
    category: str        # "mandatory" | "supplementary" | "unsupported"
    status: str
    evidence: str
    note: str = ""
    from_image: str = ""

    def to_dict(self):
        return asdict(self)


# ============================================================
# HELPERS ON THE EXTRACTOR'S OUTPUT SHAPE
# ============================================================

def field(result: dict, name: str) -> Optional[dict]:
    return (result.get("product_information") or {}).get(name)


def field_value(result: dict, name: str):
    e = field(result, name)
    if not e:
        return None
    return e.get("value") if "value" in e else e.get("values")


def field_text(result: dict, name: str) -> str:
    """Everything OCR ever associated with this field - label + evidence -
    so format checks (e.g. the tax clause) can look past the parsed value."""
    e = field(result, name)
    if not e:
        return ""
    parts = [str(e.get("label", ""))]
    parts += [str(x) for x in e.get("evidence", [])]
    v = e.get("value")
    if v:
        parts.append(str(v))
    return " ".join(parts)


def field_confidence(result: dict, name: str) -> float:
    e = field(result, name)
    if not e:
        return 0.0
    vals = [e[k] for k in ("label_confidence", "value_confidence") if k in e]
    return sum(vals) / len(vals) if vals else 0.5


def source_of(result: dict, name: str) -> str:
    e = field(result, name) or {}
    return e.get("from_image", "") or os.path.basename(result.get("source_image", ""))


def extraction_is_trustworthy(result: dict) -> bool:
    """False = OCR quality was poor enough that a missing field probably
    means 'OCR missed it', not 'the label omits it'. Governs FAIL vs REVIEW
    for every absence check below."""
    q = result.get("quality", {})
    regions = q.get("ocr_regions", 0)
    conf = q.get("mean_confidence", 0.0)
    return regions >= 15 and conf >= 0.62


def has_section_like(result: dict, *keys) -> bool:
    sections = result.get("sections") or {}
    return any(k in sections for k in keys)


def looks_like_food(result: dict) -> bool:
    """FSSAI licensing is a Food Safety Act requirement, not Legal Metrology -
    only meaningful to check on something that looks like a food item."""
    if has_section_like(result, "ingredients", "nutrition", "allergen"):
        return True
    if field_value(result, "fssai_license"):
        return True
    return False


def absence_status(result: dict, evidence_name: str = "") -> tuple:
    """Standard verdict for 'this field was not found at all'."""
    if extraction_is_trustworthy(result):
        return FAIL, "Not found on any provided image; scan quality was good " \
                     "enough that this likely means the label omits it."
    return REVIEW, "Not found, but OCR quality on this image was weak - " \
                   "this may be an extraction miss rather than a real omission."


# ============================================================
# RULES
# Each check(result) -> Verdict. Ordering matches how an officer
# would scan a label: identity, quantity, price, dates, batch,
# contact, then category-specific and unsupported items.
# ============================================================

def check_manufacturer(result):
    e = field(result, "manufacturer") or field(result, "marketed_by")
    if e and (e.get("value") or e.get("values")):
        src = e.get("from_image") or source_of(result, "manufacturer")
        return Verdict("LM-1", "Manufacturer / packer / importer identified",
                       "Rule 6(1)(a)", "mandatory", PASS,
                       str(e.get("value") or e.get("values")), from_image=src)
    status, note = absence_status(result)
    return Verdict("LM-1", "Manufacturer / packer / importer identified",
                   "Rule 6(1)(a)", "mandatory", status, "", note)


def check_net_quantity(result):
    e = field(result, "net_quantity")
    val = field_value(result, "net_quantity")
    if not val:
        status, note = absence_status(result)
        return Verdict("LM-2", "Net quantity declared in standard units",
                       "Rule 6(1)(c) / Rule 8", "mandatory", status, "", note)
    has_unit = bool(re.search(r"\d\s*(mg|g|kg|ml|ltr?|l|litres?)\b", val, re.I))
    conf = field_confidence(result, "net_quantity")
    if has_unit:
        return Verdict("LM-2", "Net quantity declared in standard units",
                       "Rule 6(1)(c) / Rule 8", "mandatory", PASS, val,
                       from_image=source_of(result, "net_quantity"))
    if conf < 0.6:
        return Verdict("LM-2", "Net quantity declared in standard units",
                       "Rule 6(1)(c) / Rule 8", "mandatory", REVIEW, val,
                       "A quantity was found but the unit is unclear; "
                       "low OCR confidence.", source_of(result, "net_quantity"))
    return Verdict("LM-2", "Net quantity declared in standard units",
                   "Rule 6(1)(c) / Rule 8", "mandatory", FAIL, val,
                   "A number was found but no recognised SI unit "
                   "(g/kg/ml/l) is attached to it.",
                   source_of(result, "net_quantity"))


def check_mrp_present(result):
    val = field_value(result, "mrp")
    if val:
        return Verdict("LM-3", "Maximum Retail Price declared",
                       "Rule 6(1)(d)", "mandatory", PASS, val,
                       from_image=source_of(result, "mrp"))
    status, note = absence_status(result)
    return Verdict("LM-3", "Maximum Retail Price declared",
                   "Rule 6(1)(d)", "mandatory", status, "", note)


def check_mrp_tax_clause(result):
    val = field_value(result, "mrp")
    if not val:
        return Verdict("LM-4", "MRP carries the 'inclusive of all taxes' clause",
                       "Rule 18", "mandatory", NOT_APPLICABLE, "",
                       "Skipped - no MRP was found (see LM-3).")
    text = field_text(result, "mrp")
    if re.search(r"incl\w*.{0,25}?tax", text, re.I) or \
       re.search(r"tax\w*.{0,25}?incl", text, re.I):
        return Verdict("LM-4", "MRP carries the 'inclusive of all taxes' clause",
                       "Rule 18", "mandatory", PASS, text.strip()[:80],
                       from_image=source_of(result, "mrp"))
    conf = field_confidence(result, "mrp")
    status = REVIEW if conf < 0.6 else FAIL
    return Verdict("LM-4", "MRP carries the 'inclusive of all taxes' clause",
                   "Rule 18", "mandatory", status, val,
                   "MRP found but no tax-inclusive wording detected nearby - "
                   "confirm against the actual pack.", source_of(result, "mrp"))


def check_mfg_date(result):
    val = field_value(result, "manufacturing_date")
    if val:
        return Verdict("LM-5", "Month & year of manufacture/packing declared",
                       "Rule 6(1)(e)", "mandatory", PASS, val,
                       from_image=source_of(result, "manufacturing_date"))
    status, note = absence_status(result)
    return Verdict("LM-5", "Month & year of manufacture/packing declared",
                   "Rule 6(1)(e)", "mandatory", status, "", note)


def check_expiry_date(result):
    val = field_value(result, "expiry_date")
    if val:
        return Verdict("LM-6", "Best-before / use-by / expiry declared",
                       "Rule 6(1)(e) proviso", "mandatory", PASS, val,
                       from_image=source_of(result, "expiry_date"))
    status, note = absence_status(result)
    if status == FAIL:
        note += " Not all commodities require a shelf-life date - " \
                "confirm this product category needs one before citing."
    return Verdict("LM-6", "Best-before / use-by / expiry declared",
                   "Rule 6(1)(e) proviso", "mandatory", status, "", note)


def check_batch(result):
    val = field_value(result, "batch_number")
    if val:
        return Verdict("LM-7", "Batch / lot / code number declared",
                       "Rule 6(1)(f)", "mandatory", PASS, val,
                       from_image=source_of(result, "batch_number"))
    status, note = absence_status(result)
    return Verdict("LM-7", "Batch / lot / code number declared",
                   "Rule 6(1)(f)", "mandatory", status, "", note)


def check_consumer_care(result):
    e = field(result, "customer_care")
    contacts = result.get("contacts") or {}
    has_any = bool((e and e.get("value")) or contacts.get("phones")
                   or contacts.get("emails") or contacts.get("websites"))
    if has_any:
        bits = []
        if e and e.get("value"):
            bits.append(str(e["value"]))
        bits += contacts.get("phones", []) + contacts.get("emails", [])
        return Verdict("LM-8", "Consumer complaint / care channel declared",
                       "Rule 6(1)(b) proviso", "mandatory", PASS,
                       ", ".join(bits)[:100], from_image=source_of(result, "customer_care"))
    status, note = absence_status(result)
    return Verdict("LM-8", "Consumer complaint / care channel declared",
                   "Rule 6(1)(b) proviso", "mandatory", status, "", note)


def check_country_of_origin(result):
    val = field_value(result, "country_of_origin")
    if val:
        return Verdict("LM-9", "Country of origin declared",
                       "2018 amendment (imported goods only)", "mandatory",
                       PASS, val, from_image=source_of(result, "country_of_origin"))
    return Verdict("LM-9", "Country of origin declared",
                   "2018 amendment (imported goods only)", "mandatory",
                   NOT_APPLICABLE, "",
                   "No origin declaration found. This clause only binds "
                   "imported goods; nothing here indicates whether this "
                   "product is imported, so it is not scored either way.")


def check_fssai(result):
    if not looks_like_food(result):
        return Verdict("SUP-1", "FSSAI licence number present",
                       "FSSAI Act, 2006 (not Legal Metrology)", "supplementary",
                       NOT_APPLICABLE, "", "No food-item indicators "
                       "(ingredients/nutrition/allergen) were found.")
    val = field_value(result, "fssai_license")
    if val:
        return Verdict("SUP-1", "FSSAI licence number present",
                       "FSSAI Act, 2006 (not Legal Metrology)", "supplementary",
                       PASS, str(val), from_image=source_of(result, "fssai_license"))
    status, note = absence_status(result)
    return Verdict("SUP-1", "FSSAI licence number present",
                   "FSSAI Act, 2006 (not Legal Metrology)", "supplementary",
                   status, "", note)


def check_product_name(result):
    return Verdict("UNSUP-1", "Common / generic name of commodity declared",
                   "Rule 6(1)(b)", "unsupported", NOT_CHECKED, "",
                   "product_reader has no product-name field yet - "
                   "this clause cannot be judged from its output.")


def check_letter_height(result):
    return Verdict("UNSUP-2", "Declaration letter/numeral height meets "
                   "minimum size", "Rule 7", "unsupported", NOT_CHECKED, "",
                   "Requires a physical scale reference (e.g. a marker of "
                   "known size) in the photo; a plain photo has no absolute "
                   "scale, so pixel height cannot be converted to millimetres.")


def check_language(result):
    return Verdict("UNSUP-3", "Declaration present in Hindi as well as English",
                   "Rule 4", "unsupported", NOT_CHECKED, "",
                   "The extractor's label matching is English-alias-only "
                   "today, so it cannot confirm or deny a Hindi declaration.")


RULES = [
    check_manufacturer, check_net_quantity, check_mrp_present,
    check_mrp_tax_clause, check_mfg_date, check_expiry_date, check_batch,
    check_consumer_care, check_country_of_origin, check_fssai,
    check_product_name, check_letter_height, check_language,
]


# ============================================================
# SCORING
# ============================================================

def run_compliance(result: dict) -> dict:
    verdicts = [rule(result) for rule in RULES]

    mandatory = [v for v in verdicts if v.category == "mandatory"]
    scored = [v for v in mandatory if v.status in STATUS_WEIGHT]
    score = (round(100 * sum(STATUS_WEIGHT[v.status] for v in scored)
                   / len(scored), 1) if scored else None)

    failed = [v for v in mandatory if v.status == FAIL]
    reviewed = [v for v in verdicts if v.status == REVIEW]
    unsupported = [v for v in verdicts if v.category == "unsupported"]

    if failed:
        overall = "NON_COMPLIANT"
    elif any(v.status == REVIEW for v in mandatory):
        overall = "NEEDS_REVIEW"
    elif score == 100.0:
        overall = "COMPLIANT"
    else:
        overall = "PARTIALLY_CHECKED"

    return {
        "success": True,
        "source": result.get("source_image") or result.get("product"),
        "overall_status": overall,
        "compliance_score_percent": score,
        "mandatory_checked": len(scored),
        "mandatory_failed": len(failed),
        "needs_review_count": len(reviewed),
        "unsupported_clause_count": len(unsupported),
        "verdicts": [v.to_dict() for v in verdicts],
        "disclaimer": (
            "Automated pre-screening only. NOT_CHECKED and NOT_APPLICABLE "
            "clauses were not evaluated by this software and require manual "
            "verification. This is not a substitute for a certified Legal "
            "Metrology officer's inspection."
        ),
    }




STATUS_ICON = {PASS: "[PASS]", FAIL: "[FAIL]", REVIEW: "[REVIEW]",
              NOT_APPLICABLE: "[ N/A ]", NOT_CHECKED: "[ SKIP ]"}


def display_compliance(report: dict):
    print()
    print("=" * 78)
    print(f"COMPLIANCE REPORT - {report.get('source', '')}")
    print("=" * 78)
    score = report["compliance_score_percent"]
    print(f"Overall status : {report['overall_status']}")
    print(f"Score          : {score if score is not None else 'n/a'}%  "
          f"({report['mandatory_checked']} mandatory clauses scored)")
    if report["needs_review_count"]:
        print(f"  ! {report['needs_review_count']} item(s) need manual review "
              f"(low OCR confidence, not a confirmed violation)")
    if report["unsupported_clause_count"]:
        print(f"  ! {report['unsupported_clause_count']} clause(s) this "
              f"software cannot check at all yet")
    print()
    for v in report["verdicts"]:
        icon = STATUS_ICON.get(v["status"], v["status"])
        print(f"{icon} {v['rule_id']:8} {v['title']}")
        print(f"          clause: {v['clause']}")
        if v["evidence"]:
            print(f"          found : {v['evidence']}")
        if v["note"]:
            print(f"          note  : {v['note']}")
        print()
    print("-" * 78)
    print(report["disclaimer"])


def select_image_dialog(multiple=False):
    try:
        from tkinter import Tk, filedialog
    except Exception:
        return []
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    types = [("Image files", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
             ("All files", "*.*")]
    if multiple:
        picked = filedialog.askopenfilenames(
            title="Select ALL images of this product (Ctrl+click)",
            filetypes=types)
        root.destroy()
        return list(picked)
    path = filedialog.askopenfilename(title="Select Product Image",
                                      filetypes=types)
    root.destroy()
    return [path] if path else []


def collect_inputs(args):
    paths = []
    for item in args.images or []:
        if os.path.isdir(item):
            for ext in ("jpg", "jpeg", "png", "bmp", "webp", "tif", "tiff"):
                paths += glob.glob(os.path.join(item, f"*.{ext}"))
                paths += glob.glob(os.path.join(item, f"*.{ext.upper()}"))
        else:
            paths += glob.glob(item) or [item]
    if not paths:
        paths = select_image_dialog(multiple=args.merge or args.pick)
    return sorted(set(p for p in paths if p))


def main():
    ap = argparse.ArgumentParser(
        description="Product label reader + Legal Metrology compliance "
                    "checker, in one pass (SIH 26034). Select or pass an "
                    "image; it is read, structured, and judged against the "
                    "Legal Metrology (Packaged Commodities) Rules, 2011.")
    ap.add_argument("images", nargs="*", help="image file(s), folder, or glob")
    ap.add_argument("-o", "--outdir", default="output")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--accurate", action="store_true",
                    help="use PP-OCRv5 server models (slower, more accurate)")
    ap.add_argument("--tile", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--no-rotate", action="store_true")
    ap.add_argument("--no-deskew", action="store_true")
    ap.add_argument("--unwarp", action="store_true",
                    help="enable doc unwarping (curved packets/bottles)")
    ap.add_argument("--det-side", type=int, default=1536)
    ap.add_argument("--min-conf", type=float, default=0.45)
    ap.add_argument("--debug", action="store_true",
                    help="write an overlay image showing detected boxes")
    ap.add_argument("--quiet", action="store_true",
                    help="save the JSON files but do not print the reports")
    ap.add_argument("--merge", action="store_true",
                    help="treat ALL input images as ONE product (front + "
                         "back + nutrition panel) before compliance-checking")
    ap.add_argument("--name", default=None,
                    help="product name for the merged output file")
    ap.add_argument("--pick", action="store_true",
                    help="open the file dialog allowing multiple images "
                         "even when not merging")
    args = ap.parse_args()

    cfg = Config(lang=args.lang, accurate=args.accurate, tile=args.tile,
                 auto_rotate=not args.no_rotate, deskew=not args.no_deskew,
                 doc_unwarping=args.unwarp, det_side_len=args.det_side,
                 min_confidence=args.min_conf, debug=args.debug)

    paths = collect_inputs(args)
    if not paths:
        print("No image selected.")
        return 1

    os.makedirs(args.outdir, exist_ok=True)
    print("Loading OCR models ...")
    engine = Engine(cfg)
    print(f"Ready (paddleocr api='{engine.mode}').\n")

    failures = 0
    collected = []
    if args.merge:
        print(f"Merging {len(paths)} image(s) into one product record.\n")

    for path in paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        t0 = time.time()
        try:
            regions, layout, image, meta = read_image(engine, path, cfg)
            result = arrange(regions, layout, meta, path)
            result["elapsed_seconds"] = round(time.time() - t0, 2)

            out_json = os.path.join(args.outdir, f"{stem}_result.json")
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            if cfg.debug:
                dbg = draw_debug(image, regions,
                                 os.path.join(args.outdir, f"{stem}_debug.jpg"))
                result["debug_image"] = dbg

            collected.append(result)
            print(f"[ok] {path}  ->  {out_json}  ({result['elapsed_seconds']}s, "
                  f"{len(regions)} regions)")

            if not args.merge:
                # Single-image mode: extraction and compliance both run NOW,
                # per image — this is the "run it and get an answer path."
                report = run_compliance(result)

                comp_path = os.path.join(
                    args.outdir,
                    f"{stem}_compliance.json"
                )

                with open(comp_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)

                # FSSAI regulatory validation
                fssai_report = check_ocr_result(
                    result,
                    FSSAI_RULES_FILE,
                )

                fssai_path = os.path.join(
                    args.outdir,
                    f"{stem}_fssai_compliance.json",
                )

                with open(fssai_path, "w", encoding="utf-8") as f:
                    json.dump(
                        fssai_report,
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )

                print(
                    f"[ok] FSSAI compliance -> {fssai_path} "
                    f"({fssai_report['overall_status']})"
                )

                print(
                    f"[ok] compliance -> {comp_path} "
                    f"({report['overall_status']}, "
                    f"{report['compliance_score_percent']}%)"
                )

                if not args.quiet:
                    display_result(result)
                    display_compliance(report)
        except Exception as exc:
                    failures += 1
                    print(f"[fail] {path}: {exc}")
                    if cfg.debug:
                        import traceback
                        traceback.print_exc()

        if args.merge and collected:
                    # Merged mode: ALL images are one product. Compliance runs ONCE on
                    # the combined record, not once per photo - a date on the back and
                    # an MRP on the front both count toward the SAME verdict.
                    name = args.name or os.path.splitext(
                        os.path.basename(collected[0].get("source_image", "product")))[0]
                    merged = merge_results(collected, label=name)
                    out_json = os.path.join(args.outdir, f"{name}_merged.json")
                    with open(out_json, "w", encoding="utf-8") as f:
                        json.dump(merged, f, indent=2, ensure_ascii=False)
                    print(f"\n[merged] {len(collected)} image(s) -> {out_json}")

                    report = run_compliance(merged)
                    comp_path = os.path.join(args.outdir, f"{name}_compliance.json")
                    with open(comp_path, "w", encoding="utf-8") as f:
                        json.dump(report, f, indent=2, ensure_ascii=False)
                    print(f"[merged] compliance -> {comp_path}  "
                        f"({report['overall_status']}, "
                        f"{report['compliance_score_percent']}%)")
                    if not args.quiet:
                        display_merged(merged)
                        display_compliance(report)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
