#!/usr/bin/env python3
# ============================================================
# LEGAL METROLOGY COMPLIANCE ENGINE  -  V1
# SIH 2026 - Problem Statement 26034
# ============================================================
# Stage 2/3 of the pipeline: takes the JSON produced by
# product_reader (single-image *_result.json OR *_merged.json)
# and judges it against the Legal Metrology (Packaged
# Commodities) Rules, 2011 - not just "was text found" but
# "does this satisfy the declaration the law requires".
#
# Deliberately NOT part of product_reader.py: extraction and
# compliance are different jobs done by different people in a
# real inspection pipeline, and keeping them separate means a
# rule can be fixed without touching the OCR code, and vice
# versa. Point this at any *_result.json or *_merged.json.
#
# WHAT THIS DOES NOT DO (see README at bottom of --help):
#   - Cannot verify printed letter/numeral height (Rule 7) -
#     that needs a physical scale reference in the photo, which
#     product_reader does not capture. Reported as NOT_CHECKED,
#     never silently skipped.
#   - Cannot confirm Hindi declaration presence (Rule 4) - the
#     extractor is English-alias-only today.
#   - Cannot confirm "common/generic name of the commodity" -
#     product_reader has no product_name field yet.
# These are named explicitly in every report so nobody mistakes
# "not checked" for "compliant".
# ============================================================

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional

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


# ============================================================
# DISPLAY
# ============================================================

STATUS_ICON = {PASS: "[PASS]", FAIL: "[FAIL]", REVIEW: "[REVIEW]",
              NOT_APPLICABLE: "[ N/A ]", NOT_CHECKED: "[ SKIP ]"}


def display(report: dict):
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


# ============================================================
# CLI
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(
        description="Legal Metrology compliance engine (SIH 26034, stage 2/3). "
                    "Reads *_result.json or *_merged.json produced by "
                    "product_reader and judges it against the Legal "
                    "Metrology (Packaged Commodities) Rules, 2011.")
    ap.add_argument("inputs", nargs="+",
                    help="path(s) to *_result.json / *_merged.json, or a glob")
    ap.add_argument("-o", "--outdir", default="output")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    paths = []
    for item in args.inputs:
        paths += glob.glob(item) or [item]
    paths = sorted(set(paths))

    os.makedirs(args.outdir, exist_ok=True)
    for path in paths:
        try:
            result = load_json(path)
        except Exception as exc:
            print(f"[fail] {path}: could not read/parse JSON: {exc}")
            continue
        report = run_compliance(result)
        stem = os.path.splitext(os.path.basename(path))[0]
        out_path = os.path.join(args.outdir, f"{stem}_compliance.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[ok] {path} -> {out_path}  "
              f"({report['overall_status']}, {report['compliance_score_percent']}%)")
        if not args.quiet:
            display(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
