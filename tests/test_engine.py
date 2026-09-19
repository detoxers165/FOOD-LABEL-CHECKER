import json
import tempfile
from pathlib import Path

from regulation.engine import (
    RegulationEngine,
    DECISION_COLUMN,
    DECISION_NON_COMPLIANT,
    DECISION_UNKNOWN,
)


RULES = Path(__file__).parent.parent / "regulation" / "rules.json"


def test_identity_by_ins():
    engine = RegulationEngine(RULES)
    out = engine.resolve_additive({
        "declared_name": "curcumin",
        "ins": "100(i)",
        "amount": 10,
        "unit": "mg/kg",
    })
    assert out["normalized_name"] == "Curcumin"
    assert out["technical_function"] == "Colour"


def test_unknown_identity_is_not_called_unsafe():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {
            "declared_name": "Example",
            "resolved_category": None,
            "ingredients": ["mystery additive"],
        },
        "additives": [{
            "declared_name": "mystery additive",
            "ins": None,
            "amount": None,
            "unit": None,
        }],
        "measurements": [],
    })
    assert result["overall_status"] in {DECISION_UNKNOWN, DECISION_COLUMN}
    assert any("identity" in w["message"].lower() for w in result["warnings"])


def test_current_appendix_a_tables_are_deferred():
    engine = RegulationEngine(RULES)
    result = engine.check({
        "product": {
            "declared_name": "Bread",
            "resolved_category": "BREAD",
            "ingredients": ["flour", "sodium fumarate"],
        },
        "additives": [{
            "declared_name": "Sodium fumarate",
            "ins": None,
            "amount": 100,
            "unit": "mg/kg",
        }],
        "measurements": [],
    })
    assert result["overall_status"] in {DECISION_COLUMN, DECISION_UNKNOWN}
    assert any(
        x["status"] == DECISION_COLUMN
        for x in result["deferred_checks"]
    )


def test_unit_conversion():
    from regulation.engine import convert_amount
    assert convert_amount(1, "g/kg", "mg/kg") == 1000
    assert convert_amount(1000, "mg/kg", "g/kg") == 1
    assert convert_amount(1, "%", "mg/kg") == 10000
    assert convert_amount(1, "ppm", "mg/kg") == 1
