#!/usr/bin/env python3
"""
Food Label Checker - High-Performance Backend API Server
=========================================================
Integrates PaddleOCR image reading, Legal Metrology compliance engine,
and FSSAI regulatory engine with the React frontend.

Provides:
- GET  /api/health       -> System health & backend connectivity status
- POST /api/scan         -> Multi-part image upload with OCR & full regulatory audit
- POST /api/analyze-text -> Direct text/ingredient list input analysis
"""

from __future__ import annotations

import os
import re
import sys
import time
import uuid
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Paddle & Environment settings
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

from config import get_settings
from database.mongodb import MongoDatabase
from database.indexes import ensure_indexes
from routes.auth_routes import auth_router
from errors import AppError
from response import error_response

# Import project engines
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

try:
    from product_compliance_tool import (
        Config,
        Engine,
        read_image,
        arrange,
        run_compliance,
        FSSAI_RULES_FILE,
    )
    from regulation.label_pipeline import (
        check_ocr_result,
        check_label,
        extract_ingredient_list,
        build_additives_from_text,
    )
    OCR_ENGINE_AVAILABLE = True
except Exception as e:
    print(f"Warning: OCR engine import failed: {e}", file=sys.stderr)
    OCR_ENGINE_AVAILABLE = False
    FSSAI_RULES_FILE = str(BASE_DIR / "regulation" / "rules.json")

# ---------------------------------------------------------------------------
# Knowledge Base & Supplementary Reference Data (Codex / FSSAI)
# ---------------------------------------------------------------------------
KNOWN_INS_DB: Dict[str, Dict[str, str]] = {
    "100": {"name": "Curcumin", "category": "Natural Color", "limit": "GMP", "desc": "Natural yellow pigment extracted from turmeric rhizome."},
    "100(i)": {"name": "Curcumin", "category": "Natural Color", "limit": "GMP", "desc": "Natural yellow pigment extracted from turmeric rhizome."},
    "101": {"name": "Riboflavin (Vitamin B2)", "category": "Food Color / Vitamin", "limit": "50 ppm", "desc": "Yellow-orange micronutrient colorant."},
    "102": {"name": "Tartrazine", "category": "Synthetic Color", "limit": "100 ppm", "desc": "Permitted synthetic lemon-yellow azo food dye."},
    "110": {"name": "Sunset Yellow FCF", "category": "Synthetic Color", "limit": "50 ppm", "desc": "Synthetic orange-yellow dye; requires warning label for children."},
    "122": {"name": "Azorubine / Carmoisine", "category": "Synthetic Color", "limit": "100 ppm", "desc": "Permitted synthetic red azo dye."},
    "124": {"name": "Ponceau 4R", "category": "Synthetic Color", "limit": "50 ppm", "desc": "Permitted synthetic strawberry red dye."},
    "127": {"name": "Erythrosine", "category": "Synthetic Color", "limit": "100 ppm", "desc": "Cherry-pink synthetic fluorone dye."},
    "132": {"name": "Indigo Carmine", "category": "Synthetic Color", "limit": "100 ppm", "desc": "Permitted synthetic blue colorant."},
    "133": {"name": "Brilliant Blue FCF", "category": "Synthetic Color", "limit": "100 ppm", "desc": "Permitted triarylmethane synthetic blue dye."},
    "140": {"name": "Chlorophyll", "category": "Natural Color", "limit": "GMP", "desc": "Natural green pigment from leafy plants."},
    "150a": {"name": "Plain Caramel", "category": "Natural Color", "limit": "GMP", "desc": "Naturally derived heat-treated sugar colorant."},
    "150c": {"name": "Ammonia Caramel", "category": "Colorant", "limit": "GMP", "desc": "Class III caramel color."},
    "150d": {"name": "Sulphite Ammonia Caramel", "category": "Colorant", "limit": "GMP", "desc": "Class IV caramel color widely used in beverages."},
    "160a": {"name": "Beta-Carotene", "category": "Color / Provitamin A", "limit": "100 ppm", "desc": "Natural plant precursor to Vitamin A."},
    "160b": {"name": "Annatto", "category": "Natural Color", "limit": "100 ppm", "desc": "Natural red-orange condiment and colorant."},
    "200": {"name": "Sorbic Acid", "category": "Preservative", "limit": "1000 ppm", "desc": "Antimicrobial preservative preventing mold and yeasts."},
    "202": {"name": "Potassium Sorbate", "category": "Preservative", "limit": "250 ppm", "desc": "Antimicrobial salt preventing mold, yeast, and fungi."},
    "211": {"name": "Sodium Benzoate", "category": "Preservative", "limit": "200 ppm", "desc": "Broad-spectrum chemical preservative under strict statutory limits."},
    "220": {"name": "Sulphur Dioxide", "category": "Preservative / Antioxidant", "limit": "70 ppm", "desc": "Bleaching and antimicrobial agent; allergen trigger."},
    "222": {"name": "Sodium Bisulphite", "category": "Preservative", "limit": "100 ppm", "desc": "Sulphite preservative and antioxidant."},
    "224": {"name": "Potassium Metabisulphite", "category": "Preservative", "limit": "100 ppm", "desc": "Antimicrobial sulphite widely used in juices and dried fruits."},
    "250": {"name": "Sodium Nitrite", "category": "Preservative / Curing Agent", "limit": "100 ppm", "desc": "Preservative used in cured meats; strictly controlled."},
    "260": {"name": "Acetic Acid", "category": "Acidity Regulator", "limit": "GMP", "desc": "Naturally occurring organic acid giving vinegar its pungency."},
    "270": {"name": "Lactic Acid", "category": "Acidity Regulator", "limit": "GMP", "desc": "Natural fermentation acid used for pH regulation."},
    "282": {"name": "Calcium Propionate", "category": "Preservative", "limit": "2000 ppm", "desc": "Preservative used widely in baked goods to inhibit mold."},
    "300": {"name": "Ascorbic Acid (Vitamin C)", "category": "Antioxidant", "limit": "GMP", "desc": "Natural antioxidant and essential dietary vitamin."},
    "306": {"name": "Mixed Tocopherols (Vitamin E)", "category": "Antioxidant", "limit": "GMP", "desc": "Natural lipid-soluble antioxidant."},
    "319": {"name": "TBHQ", "category": "Antioxidant", "limit": "200 ppm", "desc": "Synthetic aromatic organic compound used as fat stabilizer."},
    "320": {"name": "BHA (Butylated Hydroxyanisole)", "category": "Antioxidant", "limit": "200 ppm", "desc": "Synthetic antioxidant protecting vegetable oils from rancidity."},
    "321": {"name": "BHT (Butylated Hydroxytoluene)", "category": "Antioxidant", "limit": "100 ppm", "desc": "Synthetic fat-soluble antioxidant."},
    "322": {"name": "Lecithins", "category": "Emulsifier", "limit": "GMP", "desc": "Natural fatty substance from soy or egg yolk; allergen trigger for soy."},
    "330": {"name": "Citric Acid", "category": "Acidity Regulator / Acidulant", "limit": "GMP / GRAS", "desc": "Naturally derived citrus acidifier; safe under GMP standards."},
    "331": {"name": "Sodium Citrates", "category": "Acidity Regulator", "limit": "GMP", "desc": "Buffering agent and emulsion stabilizer."},
    "334": {"name": "Tartaric Acid", "category": "Acidity Regulator", "limit": "GMP", "desc": "Natural organic acid providing crisp tartness."},
    "407": {"name": "Carrageenan", "category": "Thickener / Stabilizer", "limit": "GMP", "desc": "Natural polysaccharide extracted from red edible seaweeds."},
    "412": {"name": "Guar Gum", "category": "Thickener / Stabilizer", "limit": "GMP", "desc": "Natural legume galactomannan polysaccharide."},
    "415": {"name": "Xanthan Gum", "category": "Thickener / Stabilizer", "limit": "GMP", "desc": "Bacterial polysaccharide stabilizer providing texture."},
    "420": {"name": "Sorbitol", "category": "Sweetener / Humectant", "limit": "GMP", "desc": "Slowly metabolized sugar alcohol; mild laxative warning at high doses."},
    "422": {"name": "Glycerol", "category": "Humectant / Solvent", "limit": "GMP", "desc": "Safe polyol compound used to retain moisture."},
    "440": {"name": "Pectins", "category": "Gelling Agent", "limit": "GMP", "desc": "Naturally occurring structural acid found in citrus fruits."},
    "452": {"name": "Polyphosphates", "category": "Stabilizer / Emulsifier", "limit": "5000 ppm", "desc": "Water retention and processing aid."},
    "471": {"name": "Mono- and Diglycerides of Fatty Acids", "category": "Emulsifier", "limit": "GMP", "desc": "Widely used food emulsifier derived from plant oils."},
    "500": {"name": "Sodium Carbonates", "category": "Raising Agent", "limit": "GMP", "desc": "Baking soda & mineral salts aiding aeration in baking."},
    "503": {"name": "Ammonium Carbonates", "category": "Raising Agent", "limit": "GMP", "desc": "Traditional baking leavener that evaporates cleanly upon baking."},
    "551": {"name": "Silicon Dioxide (Amorphous)", "category": "Anticaking Agent", "limit": "10000 ppm", "desc": "Flow-aid mineral used in powdery food mixes."},
    "621": {"name": "Monosodium Glutamate (MSG)", "category": "Flavor Enhancer", "limit": "1800 ppm", "desc": "Savory umami flavor enhancer; restricted for infant foods."},
    "627": {"name": "Disodium Guanylate", "category": "Flavor Enhancer", "limit": "GMP", "desc": "Purine ribonucleotide flavor booster paired with MSG."},
    "631": {"name": "Disodium Inosinate", "category": "Flavor Enhancer", "limit": "GMP", "desc": "Synergistic umami enhancer."},
    "924": {"name": "Potassium Bromate", "category": "Prohibited Bleaching Agent", "limit": "PROHIBITED", "desc": "Strictly banned in India under FSSAI due to carcinogenic health risks."},
    "950": {"name": "Acesulfame Potassium", "category": "Artificial Sweetener", "limit": "1000 ppm", "desc": "Calorie-free sugar substitute; requires mandatory statutory disclosure."},
    "951": {"name": "Aspartame", "category": "Artificial Sweetener", "limit": "700 ppm", "desc": "High-intensity artificial sweetener; contraindicated for phenylketonurics."},
    "954": {"name": "Saccharin", "category": "Artificial Sweetener", "limit": "100 ppm", "desc": "Intense non-nutritive sweetener subject to strict ceiling limits."},
    "955": {"name": "Sucralose", "category": "Artificial Sweetener", "limit": "750 ppm", "desc": "Chlorinated zero-calorie artificial sweetener."},
    "960": {"name": "Steviol Glycosides (Stevia)", "category": "Natural Sweetener", "limit": "200 ppm", "desc": "Natural high-potency plant sweetener extracted from Stevia rebaudiana."},
}

COMMON_ALLERGENS = [
    ("Gluten / Wheat", re.compile(r"\b(wheat|gluten|barley|rye|maida|semolina|atta|spelt)\b", re.IGNORECASE)),
    ("Milk / Dairy", re.compile(r"\b(milk|dairy|whey|casein|butter|cheese|ghee|cream|lactose)\b", re.IGNORECASE)),
    ("Soy / Soybeans", re.compile(r"\b(soy|soya|soybean|lecithin)\b", re.IGNORECASE)),
    ("Peanuts / Tree Nuts", re.compile(r"\b(peanut|groundnut|almond|cashew|walnut|pistachio|hazelnut)\b", re.IGNORECASE)),
    ("Eggs", re.compile(r"\b(egg|albumin|egg powder|ovalbumin)\b", re.IGNORECASE)),
    ("Fish / Shellfish", re.compile(r"\b(fish|prawn|shrimp|crab|shellfish|gelatin)\b", re.IGNORECASE)),
    ("Sulphites", re.compile(r"\b(sulphite|sulfite|metabisulphite|ins\s*22\d)\b", re.IGNORECASE)),
    ("Sesame", re.compile(r"\b(sesame|til)\b", re.IGNORECASE)),
]

# ---------------------------------------------------------------------------
# FastAPI Application & Models
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    mongo = MongoDatabase(settings.mongodb_uri, settings.mongodb_database)
    await mongo.connect()
    
    app.state.db = mongo.get_database()
    await ensure_indexes(app.state.db)
    
    yield
    
    await mongo.disconnect()

app = FastAPI(
    title="Food Label Checker API",
    description="FSSAI & Legal Metrology Compliance Inspection Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins or ["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return error_response(
        exc.code,
        exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )

# Global lazy OCR Engine instance
_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None and OCR_ENGINE_AVAILABLE:
        cfg = Config(auto_rotate=True, deskew=True, tile="auto")
        _ocr_engine = Engine(cfg)
    return _ocr_engine


class TextAnalyzeRequest(BaseModel):
    text: str
    productName: Optional[str] = "Packaged Food Product"
    brandName: Optional[str] = None
    category: Optional[str] = None


# ---------------------------------------------------------------------------
# Response Normalization Helpers
# ---------------------------------------------------------------------------

def normalize_ins_number(code: str) -> str:
    """Cleans up INS number to canonical string, e.g. '100(i)', '211'."""
    clean = re.sub(r"[^\d(ivx)]", "", code.lower())
    # Handle roman numeral casing
    return clean.replace("i", "i").replace("v", "v").replace("x", "x")


def lookup_ins_info(ins_code: str) -> Dict[str, str]:
    """Retrieves additive identity details from the knowledge base."""
    # Try exact match
    if ins_code in KNOWN_INS_DB:
        return KNOWN_INS_DB[ins_code]
    
    # Try stripping brackets: e.g. 100(i) -> 100
    base_code = re.sub(r"\(.*?\)", "", ins_code).strip()
    if base_code in KNOWN_INS_DB:
        return KNOWN_INS_DB[base_code]

    return {
        "name": f"Food Additive (INS {ins_code})",
        "category": "Additive",
        "limit": "GMP / Prescribed Limit",
        "desc": f"Additive identified by code INS {ins_code} under FSSAI / Codex Alimentarius.",
    }


def analyze_allergens(full_text: str) -> List[str]:
    """Scans ingredient text for known major allergens."""
    detected = []
    for allergen_name, pattern in COMMON_ALLERGENS:
        if pattern.search(full_text):
            detected.append(allergen_name)
    return detected


def assemble_unified_report(
    product_name: str,
    brand_name: str,
    fssai_report: Dict[str, Any],
    lm_report: Optional[Dict[str, Any]] = None,
    ocr_meta: Optional[Dict[str, Any]] = None,
    raw_text: str = "",
) -> Dict[str, Any]:
    """Builds the unified frontend JSON response schema."""
    ingredients_list = []
    warnings_list = []

    # 1. Additives from FSSAI report
    norm_additives = fssai_report.get("normalized_additives", [])
    found_ins_set = set()

    for item in norm_additives:
        ins = str(item.get("ins") or "").strip()
        if not ins:
            continue
        found_ins_set.add(ins)
        info = lookup_ins_info(ins)
        
        # Determine status
        status = "SAFE"
        if info.get("limit") == "PROHIBITED" or item.get("identity_status") == "PROHIBITED":
            status = "EXCEEDS_LIMIT"
        elif "211" in ins or "110" in ins or "951" in ins:
            status = "MODERATE"

        # Check if FSSAI flagged any violation for this
        for v in fssai_report.get("violations", []):
            if ins in str(v):
                status = "EXCEEDS_LIMIT"

        ingredients_list.append({
            "name": item.get("normalized_name") or info["name"],
            "insNumber": f"INS {ins}",
            "category": item.get("technical_function") or info["category"],
            "detectedValue": f"{item.get('amount')} {item.get('unit')}" if item.get("amount") else "Present on label",
            "safeLimit": info["limit"],
            "status": status,
            "description": info["desc"],
        })

    # 2. Plain ingredients from product declaration
    product_dict = fssai_report.get("product", {})
    plain_ings = product_dict.get("ingredients", [])
    
    # If ingredients string is one big block, split it nicely
    if len(plain_ings) == 1 and isinstance(plain_ings[0], str):
        split_items = [p.strip() for p in plain_ings[0].split(",") if p.strip()]
        for idx, item_str in enumerate(split_items[:12]):
            # Skip if it's purely an INS match we already added
            if any(ins in item_str for ins in found_ins_set):
                continue
            ingredients_list.append({
                "name": item_str.title(),
                "insNumber": "Raw Ingredient",
                "category": "Basic Food Ingredient",
                "detectedValue": "Present",
                "safeLimit": "Permitted",
                "status": "SAFE",
                "description": "Standard declared recipe component.",
            })

    # Fallback if no ingredients were extracted
    if not ingredients_list:
        ingredients_list.append({
            "name": "General Ingredients Declared",
            "insNumber": "N/A",
            "category": "Food Mixture",
            "detectedValue": "Present",
            "safeLimit": "Statutory Standards",
            "status": "SAFE",
            "description": "Text scanned successfully. No restricted INS additives flagged.",
        })

    # 3. Assemble Warnings
    # FSSAI Violations
    for v in fssai_report.get("violations", []):
        msg = v.get("message") or str(v)
        warnings_list.append({
            "type": "REGULATORY",
            "message": f"FSSAI Violation: {msg}"
        })

    # Specific Additive Advisories
    for ins in found_ins_set:
        if ins in ("102", "110", "122", "124"):
            warnings_list.append({
                "type": "HEALTH",
                "message": f"Contains Permitted Synthetic Colour (INS {ins}): Requires statutory warning: 'May have an adverse effect on activity and attention in children'."
            })
        elif ins == "951":
            warnings_list.append({
                "type": "HEALTH",
                "message": "Contains Artificial Sweetener Aspartame (INS 951): Mandatory warning: 'Not recommended for phenylketonurics'."
            })
        elif ins == "621":
            warnings_list.append({
                "type": "HEALTH",
                "message": "Contains added Monosodium Glutamate (MSG / INS 621): Not recommended for infants below 12 months."
            })
        elif ins == "924":
            warnings_list.append({
                "type": "REGULATORY",
                "message": "CRITICAL: Potassium Bromate (INS 924) detected. Prohibited substance under FSSAI safety regulations."
            })

    # Allergens
    text_to_check = (raw_text or "") + " " + " ".join(item.get("name", "") for item in ingredients_list)
    allergens = analyze_allergens(text_to_check)
    if allergens:
        warnings_list.append({
            "type": "ALLERGEN",
            "message": f"Potential Allergens Detected: {', '.join(allergens)}. Verify allergen declarations on packaging."
        })

    # Legal Metrology Warnings
    if lm_report and lm_report.get("overall_status") == "NON_COMPLIANT":
        failed_count = lm_report.get("mandatory_failed", 0)
        warnings_list.append({
            "type": "LEGAL_METROLOGY",
            "message": f"Legal Metrology Non-Compliance: {failed_count} mandatory declaration(s) omitted or unverified under Packaged Commodities Rules."
        })

    # 4. Overall Safety Status
    overall_safety = "SAFE"
    has_violations = bool(fssai_report.get("violations")) or any(i["status"] == "EXCEEDS_LIMIT" for i in ingredients_list)
    has_caution = any(i["status"] == "MODERATE" for i in ingredients_list) or bool(warnings_list)

    if has_violations:
        overall_safety = "HIGH_RISK"
    elif has_caution:
        overall_safety = "CAUTION"

    # 5. Format Legal Metrology details
    lm_data = None
    if lm_report:
        lm_data = {
            "overallStatus": lm_report.get("overall_status", "UNKNOWN"),
            "complianceScorePercent": lm_report.get("compliance_score_percent", 0.0),
            "mandatoryChecked": lm_report.get("mandatory_checked", 0),
            "mandatoryFailed": lm_report.get("mandatory_failed", 0),
            "needsReviewCount": lm_report.get("needs_review_count", 0),
            "verdicts": [
                {
                    "ruleId": v.get("rule_id"),
                    "title": v.get("title"),
                    "clause": v.get("clause"),
                    "status": v.get("status"),
                    "evidence": v.get("evidence"),
                    "note": v.get("note"),
                }
                for v in lm_report.get("verdicts", [])
            ]
        }

    return {
        "productName": product_name or "Packaged Food Product",
        "brandName": brand_name or "Not Specified on Label",
        "overallSafety": overall_safety,
        "scanTimestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ingredients": ingredients_list,
        "warnings": warnings_list,
        "legalMetrology": lm_data,
        "fssaiSummary": {
            "status": fssai_report.get("overall_status"),
            "violations": len(fssai_report.get("violations", [])),
            "warnings": len(fssai_report.get("warnings", [])),
            "passedChecks": fssai_report.get("summary", {}).get("passed_checks", 0),
        },
        "ocrTrace": ocr_meta,
    }


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Connectivity and diagnostic health endpoint."""
    return {
        "online": True,
        "message": "FSSAI Regulation & OCR Backend Online",
        "ocrAvailable": OCR_ENGINE_AVAILABLE,
        "fssaiRulesFile": FSSAI_RULES_FILE,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.post("/api/scan")
async def scan_label(
    file: Optional[UploadFile] = File(None),
    image: Optional[UploadFile] = File(None),
):
    """Processes uploaded label photo with OCR & compliance checks."""
    upload = file or image
    if not upload:
        raise HTTPException(status_code=400, detail="No image file provided. Supply 'file' or 'image'.")

    # Save to temp directory
    temp_dir = tempfile.mkdtemp(prefix="food_label_")
    suffix = Path(upload.filename or "upload.jpg").suffix or ".jpg"
    temp_path = os.path.join(temp_dir, f"input{suffix}")

    try:
        with open(temp_path, "wb") as f:
            content = await upload.read()
            f.write(content)

        engine = get_ocr_engine()
        if not engine:
            raise HTTPException(
                status_code=500,
                detail="PaddleOCR engine is not loaded or missing dependencies.",
            )

        cfg = Config(auto_rotate=True, deskew=True, tile="auto")
        regions, layout, img, meta = read_image(engine, temp_path, cfg)
        result = arrange(regions, layout, meta, temp_path)

        # Run Legal Metrology compliance
        lm_report = run_compliance(result)

        # Run FSSAI Regulatory validation
        fssai_report = check_ocr_result(result, FSSAI_RULES_FILE)

        # Extract product identity
        prod_info = result.get("product_information", {})
        mkt = prod_info.get("marketed_by", {}).get("value")
        mfg = prod_info.get("manufacturer", {}).get("value")
        brand = mkt or mfg or "Brand / Manufacturer Detected via OCR"

        # Guess product name from top OCR text if not explicit
        top_texts = [getattr(r, "text", str(r)) for r in regions[:8] if len(getattr(r, "text", "").strip()) > 3]
        prod_name = top_texts[0] if top_texts else "Scanned Food Label"

        # Collect raw text for allergen analysis
        all_text = " ".join([getattr(r, "text", "") for r in regions])

        ocr_meta = {
            "sourceImage": upload.filename,
            "regionsCount": len(regions),
            "meanConfidence": round(result.get("quality", {}).get("mean_confidence", 0.0), 3),
            "fieldsFound": result.get("quality", {}).get("fields_found", 0),
        }

        unified = assemble_unified_report(
            product_name=prod_name,
            brand_name=brand,
            fssai_report=fssai_report,
            lm_report=lm_report,
            ocr_meta=ocr_meta,
            raw_text=all_text,
        )

        return unified

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/analyze-text")
async def analyze_text(request: TextAnalyzeRequest):
    """Directly audits a pasted ingredient list or label text against FSSAI rules."""
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text field cannot be empty.")

    prod_name = request.productName or "Food Product"
    brand_name = request.brandName or "Direct Text Evaluation"

    # Run check_label from FSSAI pipeline
    fssai_report = check_label(
        label_text=text,
        product_name=prod_name,
        rules_file=FSSAI_RULES_FILE,
        category_hint=request.category,
    )

    unified = assemble_unified_report(
        product_name=prod_name,
        brand_name=brand_name,
        fssai_report=fssai_report,
        lm_report=None,
        ocr_meta={"source": "Direct Text Input", "characterCount": len(text)},
        raw_text=text,
    )

    return unified


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Starting Food Label Checker Backend API on http://{host}:{port} ...")
    uvicorn.run(app, host=host, port=port)
