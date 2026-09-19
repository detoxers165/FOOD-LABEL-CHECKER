from pathlib import Path

from fssai_regulation_engine import (
    RegulationEngine,
    DECISION_COMPLIANT,
    DECISION_CONDITIONAL,
    DECISION_NON_COMPLIANT,
)

RULES = Path(__file__).parent.parent / "fssai_regulatory_programmable_rules.json"


def _finding(result, rule_id):
    for bucket in ("passed_checks", "violations", "deferred_checks"):
        for f in result[bucket]:
            if f["rule_id"] == rule_id:
                return f
    return None


def test_permitted_additive_within_limit_passes():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {
            "declared_name": "Cola",
            "resolved_category": "CARBONATED_BEVERAGES",
            "ingredients": ["water", "sugar", "sodium benzoate"],
        },
        "additives": [{
            "declared_name": "Sodium Benzoate",
            "ins": "211",
            "amount": 150,
            "unit": "mg/kg",
        }],
        "measurements": [],
    })
    finding = _finding(result, "PERMISSION-INS-211-CARBONATED-BEVERAGES")
    assert finding is not None
    assert finding["status"] == DECISION_COMPLIANT
    assert not any(v["rule_id"] == "PERMISSION-INS-211-CARBONATED-BEVERAGES" for v in result["violations"])


def test_permitted_additive_over_limit_is_a_violation():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {
            "declared_name": "Cola",
            "resolved_category": "CARBONATED_BEVERAGES",
            "ingredients": ["water", "sugar", "sodium benzoate"],
        },
        "additives": [{
            "declared_name": "Sodium Benzoate",
            "ins": "211",
            "amount": 500,
            "unit": "mg/kg",
        }],
        "measurements": [],
    })
    assert result["overall_status"] == DECISION_NON_COMPLIANT
    assert any(v["rule_id"] == "PERMISSION-INS-211-CARBONATED-BEVERAGES" for v in result["violations"])


def test_banned_additive_is_non_compliant_regardless_of_amount():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {
            "declared_name": "White Bread",
            "resolved_category": "BREAD",
            "ingredients": ["flour", "potassium bromate"],
        },
        "additives": [{
            "declared_name": "Potassium Bromate",
            "ins": "924",
            "amount": 1,
            "unit": "mg/kg",
        }],
        "measurements": [],
    })
    assert result["overall_status"] == DECISION_NON_COMPLIANT
    assert any(
        v["rule_id"] == "PROHIBITION-INS-924-ALL-CATEGORIES"
        for v in result["violations"]
    )
    # It's still identified correctly even though it's banned.
    normalized = result["normalized_additives"][0]
    assert normalized["normalized_name"] == "Potassium Bromate"


def test_banned_additive_by_name_without_ins():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {
            "declared_name": "Sweet Snack",
            "resolved_category": "CONFECTIONERY",
            "ingredients": ["sugar", "rhodamine b"],
        },
        "additives": [{
            "declared_name": "Rhodamine B",
            "ins": None,
            "amount": None,
            "unit": None,
        }],
        "measurements": [],
    })
    assert result["overall_status"] == DECISION_NON_COMPLIANT
    assert any(
        v["rule_id"] == "PROHIBITION-RHODAMINE-B" for v in result["violations"]
    )


def test_permission_missing_unit_defers_instead_of_guessing():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {
            "declared_name": "Cola",
            "resolved_category": "CARBONATED_BEVERAGES",
            "ingredients": ["sodium benzoate"],
        },
        "additives": [{
            "declared_name": "Sodium Benzoate",
            "ins": "211",
            "amount": None,
            "unit": None,
        }],
        "measurements": [],
    })
    assert not any(v["rule_id"] == "PERMISSION-INS-211-CARBONATED-BEVERAGES" for v in result["violations"])
    assert any(
        d["rule_id"] == "PERMISSION-INS-211-CARBONATED-BEVERAGES"
        for d in result["deferred_checks"]
    )


def test_candidate_row_only_surfaces_for_matching_additive():
    """A candidate/appendix row for one additive should not pollute the
    result for a completely unrelated product."""
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {
            "declared_name": "Cola",
            "resolved_category": "CARBONATED_BEVERAGES",
            "ingredients": ["water", "sodium benzoate"],
        },
        "additives": [{
            "declared_name": "Sodium Benzoate",
            "ins": "211",
            "amount": 150,
            "unit": "mg/kg",
        }],
        "measurements": [],
    })
    assert not any(
        d["rule_id"] == "CANDIDATE-SODIUM-FUMARATE-BREAD"
        for d in result["deferred_checks"]
    )


def test_product_standard_numeric_pass_and_fail():
    engine = RegulationEngine(RULES)
    passing = engine.check({
        "product": {"declared_name": "Toned Milk", "resolved_category": "TONED_MILK", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "milk fat", "value": 3.2, "unit": "%"}],
    })
    assert any(
        f["rule_id"] == "STANDARD-TONED-MILK-FAT" and f["status"] == DECISION_COMPLIANT
        for f in passing["passed_checks"]
    )

    failing = engine.check({
        "product": {"declared_name": "Toned Milk", "resolved_category": "TONED_MILK", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "milk fat", "value": 2.1, "unit": "%"}],
    })
    assert failing["overall_status"] == DECISION_NON_COMPLIANT
    assert any(v["rule_id"] == "STANDARD-TONED-MILK-FAT" for v in failing["violations"])


def test_contaminant_limit_exceeded():
    # See test_contaminants_and_prohibitions.py for the fuller,
    # category-scoped contaminant test coverage (real FSSAI Contaminants
    # Regulations, 2011 figures). This test just checks the basic
    # violation path still works against the "foods not specified"
    # default lead limit (2.53 mg/kg).
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {"declared_name": "Assorted Snack", "resolved_category": "SOME_UNMAPPED_CATEGORY", "ingredients": []},
        "additives": [],
        "measurements": [{"parameter": "lead", "value": 5.0, "unit": "mg/kg"}],
    })
    assert result["overall_status"] == DECISION_NON_COMPLIANT
    assert any(v["rule_id"] == "LEAD-DEFAULT" for v in result["violations"])
