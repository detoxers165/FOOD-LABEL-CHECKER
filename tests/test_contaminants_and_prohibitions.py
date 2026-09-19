from pathlib import Path

from fssai_regulation_engine import (
    RegulationEngine,
    DECISION_COMPLIANT,
    DECISION_NON_COMPLIANT,
)

RULES = Path(__file__).parent.parent / "fssai_regulatory_programmable_rules.json"


def _finding(result, rule_id):
    for bucket in ("passed_checks", "violations", "deferred_checks"):
        for f in result[bucket]:
            if f["rule_id"] == rule_id:
                return f
    return None


def test_lead_limit_is_category_specific_not_global():
    """The same 'lead' measurement must be judged against a different limit
    depending on food category -- proving the category-scoping fix works,
    not just that a single global lead rule fires."""
    engine = RegulationEngine(RULES)

    # 0.6 mg/kg lead: over the 0.5 limit for concentrated soft drinks...
    soft_drink = engine.check({
        "product": {"declared_name": "Soft Drink Concentrate", "resolved_category": "CONCENTRATED_SOFT_DRINKS", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "lead", "value": 0.6, "unit": "mg/kg"}],
    })
    assert soft_drink["overall_status"] == DECISION_NON_COMPLIANT
    assert any(v["rule_id"] == "LEAD-CONCENTRATED-SOFT-DRINKS" for v in soft_drink["violations"])

    # ...but well under the 10 mg/kg limit for baking powder.
    baking_powder = engine.check({
        "product": {"declared_name": "Baking Powder", "resolved_category": "BAKING_POWDER", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "lead", "value": 0.6, "unit": "mg/kg"}],
    })
    finding = _finding(baking_powder, "LEAD-BAKING-POWDER")
    assert finding is not None and finding["status"] == DECISION_COMPLIANT
    assert not any(v["rule_id"] == "LEAD-BAKING-POWDER" for v in baking_powder["violations"])


def test_unscoped_default_limit_used_when_no_category_specific_row():
    """A category with no dedicated lead row (e.g. plain bread) should fall
    back to the 'foods not specified' default (2.53 mg/kg), not silently
    skip the check nor incorrectly apply a different food's limit."""
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {"declared_name": "White Bread", "resolved_category": "BREAD", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "lead", "value": 3.0, "unit": "mg/kg"}],
    })
    finding = _finding(result, "LEAD-DEFAULT")
    assert finding is not None
    assert finding["status"] == DECISION_NON_COMPLIANT  # 3.0 > 2.53 default limit


def test_aflatoxin_applies_universally_regardless_of_category():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {"declared_name": "Peanut Butter", "resolved_category": "SOME_UNMAPPED_CATEGORY", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "aflatoxin", "value": 45, "unit": "ug/kg"}],
    })
    assert result["overall_status"] == DECISION_NON_COMPLIANT
    assert any(v["rule_id"] == "AFLATOXIN-DEFAULT" for v in result["violations"])


def test_banned_seafood_antibiotic_zero_tolerance():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {"declared_name": "Frozen Shrimp", "resolved_category": "SEAFOOD_SHRIMP_PRAWN_FISH_FISHERY_PRODUCTS", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "chloramphenicol", "value": 0.01, "unit": "mg/kg"}],
    })
    assert result["overall_status"] == DECISION_NON_COMPLIANT
    assert any(v["rule_id"] == "BAN-SEAFOOD-CHLORAMPHENICOL" for v in result["violations"])


def test_seafood_antibiotic_tolerance_limit():
    engine = RegulationEngine(RULES)
    within = engine.check({
        "product": {"declared_name": "Frozen Shrimp", "resolved_category": "SEAFOOD_SHRIMP_PRAWN_FISH_FISHERY_PRODUCTS", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "tetracycline", "value": 0.05, "unit": "mg/kg"}],
    })
    finding = _finding(within, "TETRACYCLINE-SEAFOOD")
    assert finding is not None and finding["status"] == DECISION_COMPLIANT

    over = engine.check({
        "product": {"declared_name": "Frozen Shrimp", "resolved_category": "SEAFOOD_SHRIMP_PRAWN_FISH_FISHERY_PRODUCTS", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "tetracycline", "value": 0.2, "unit": "mg/kg"}],
    })
    assert over["overall_status"] == DECISION_NON_COMPLIANT


def test_cream_below_minimum_milk_fat_is_a_violation():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {"declared_name": "Fresh Cream", "resolved_category": "CREAM", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "milk fat", "value": 18.0, "unit": "%"}],
    })
    assert result["overall_status"] == DECISION_NON_COMPLIANT
    assert any(v["rule_id"] == "STANDARD-CREAM-MIN-MILK-FAT" for v in result["violations"])


def test_hexane_residue_limit_is_category_scoped():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {"declared_name": "Solvent Extracted Soya Flour", "resolved_category": "SOLVENT_EXTRACTED_EDIBLE_SOYA_FLOUR", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "hexane residue", "value": 12.0, "unit": "mg/kg"}],
    })
    assert result["overall_status"] == DECISION_NON_COMPLIANT
    assert any(v["rule_id"] == "HEXANE-RESIDUE-SOLVENT-EXTRACTED-SOYA-FLOUR" for v in result["violations"])


def test_tobacco_and_nicotine_banned_as_ingredients():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {"declared_name": "Flavoured Snack", "resolved_category": "CONFECTIONERY", "ingredients": ["sugar", "tobacco extract"]},
        "additives": [{"declared_name": "Tobacco", "ins": None, "amount": None, "unit": None}],
        "measurements": [],
    })
    assert result["overall_status"] == DECISION_NON_COMPLIANT
    assert any(v["rule_id"] == "PROHIBITION-TOBACCO" for v in result["violations"])
