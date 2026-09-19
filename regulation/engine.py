"""
FSSAI deterministic regulation engine.

This engine executes only rules that are unambiguous in the supplied
fssai_regulatory_programmable_rules.json knowledge base. Rules that still
require table-column validation or category resolution are surfaced as
review states rather than guessed.

Usage:
    from fssai_regulation_engine import RegulationEngine

    engine = RegulationEngine("regulation/rules.json")
    result = engine.check({
        "product": {
            "declared_name": "Example product",
            "resolved_category": "SOME_CATEGORY",
            "ingredients": ["water", "curcumin"]
        },
        "additives": [
            {"declared_name": "Curcumin", "ins": "100(i)",
             "amount": 50, "unit": "mg/kg"}
        ],
        "measurements": []
    })
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DECISION_COMPLIANT = "COMPLIANT"
DECISION_NON_COMPLIANT = "NON_COMPLIANT"
DECISION_CONDITIONAL = "CONDITIONAL"
DECISION_NOT_EVALUABLE = "NOT_EVALUABLE_FROM_LABEL"
DECISION_UNKNOWN = "UNKNOWN_REQUIRES_REVIEW"
DECISION_COLUMN = "REQUIRES_COLUMN_VALIDATION"


def normalize_text(value: Any) -> str:
    """Normalize names/categories for deterministic matching."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"[^a-z0-9%./()\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_ins(value: Any) -> str:
    """Normalize INS identifiers while preserving sub-identifiers such as 100(i)."""
    if value is None:
        return ""
    text = str(value).strip().upper().replace(" ", "")
    return text


def _float(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def convert_amount(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """
    Convert common concentration units.

    Supported:
      mg/kg <-> g/kg
      ppm <-> mg/kg
      ppb <-> mg/kg
      percent <-> mg/kg
      percent <-> g/kg

    For this engine, ppm is treated as mg/kg and ppb as 0.001 mg/kg.
    """
    if from_unit is None or to_unit is None:
        return None

    f = normalize_text(from_unit).replace(" ", "")
    t = normalize_text(to_unit).replace(" ", "")

    aliases = {
        "mg/kg": "mg/kg",
        "mgkg": "mg/kg",
        "g/kg": "g/kg",
        "gkg": "g/kg",
        "ppm": "ppm",
        "ppb": "ppb",
        "%": "%",
        "percent": "%",
    }
    f = aliases.get(f, f)
    t = aliases.get(t, t)

    if f == t:
        return float(value)

    # Convert through mg/kg.
    to_mgkg = {
        "mg/kg": 1.0,
        "ppm": 1.0,
        "g/kg": 1000.0,
        "ppb": 0.001,
        "%": 10000.0,
    }
    if f not in to_mgkg or t not in to_mgkg:
        return None

    mgkg = float(value) * to_mgkg[f]
    return mgkg / to_mgkg[t]


@dataclass
class Finding:
    rule_id: str
    rule_type: str
    status: str
    message: str
    source: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "status": self.status,
            "message": self.message,
            "source": self.source,
            "details": self.details,
        }


class RegulationEngine:
    """Deterministic evaluator for the current programmable rule layer."""

    def __init__(self, rules_file: str | Path):
        self.rules_file = Path(rules_file)
        with self.rules_file.open("r", encoding="utf-8") as f:
            self.knowledge_base = json.load(f)

        self.rules: List[Dict[str, Any]] = self.knowledge_base.get("rules", [])
        self.rules_by_type: Dict[str, List[Dict[str, Any]]] = {}
        for rule in self.rules:
            self.rules_by_type.setdefault(rule.get("rule_type", ""), []).append(rule)

        self._identity_by_ins: Dict[str, Dict[str, Any]] = {}
        self._identity_by_name: Dict[str, Dict[str, Any]] = {}
        for rule in self.rules_by_type.get("IDENTITY", []):
            cond = rule.get("when", {})
            if cond.get("field") != "additive.ins":
                continue
            ins = normalize_ins(cond.get("value"))
            if ins:
                self._identity_by_ins[ins] = rule
            then = rule.get("then", {}).get("set", {})
            name = then.get("additive.normalized_name")
            if name:
                self._identity_by_name[normalize_text(name)] = rule

    # ---------- public API ----------

    def check(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a product and return a source-backed audit result.

        The engine never turns missing regulatory evidence into a pass/fail
        guess. It explicitly reports review/deferred states.
        """
        product = product_data.get("product") or {}
        additives = product_data.get("additives") or []
        measurements = product_data.get("measurements") or []

        result = {
            "engine": self.knowledge_base.get("engine", {}).get("name"),
            "engine_version": self.knowledge_base.get("engine", {}).get("version"),
            "overall_status": DECISION_COMPLIANT,
            "product": product,
            "normalized_additives": [],
            "violations": [],
            "warnings": [],
            "passed_checks": [],
            "deferred_checks": [],
            "sources": [],
        }

        self._validate_input(product_data, result)

        # 1. Identity normalization.
        normalized_additives = []
        for additive in additives:
            normalized = self.resolve_additive(additive)
            normalized_additives.append(normalized)
            if normalized.get("identity_status") == DECISION_UNKNOWN:
                self._add_warning(
                    result,
                    DECISION_UNKNOWN,
                    "Additive identity could not be resolved from the supplied INS/name.",
                    details={"additive": additive},
                )
            else:
                self._add_source(result, normalized.get("source", {}))
        result["normalized_additives"] = normalized_additives

        # 2. Explicit prohibitions — product-level (rare) and per-additive.
        self._evaluate_prohibitions(product_data, result)
        self._evaluate_additive_prohibitions(product_data, normalized_additives, result)

        # 3. Product standards.
        self._evaluate_product_standards(product_data, measurements, result)

        # 4. Additive permissions.
        self._evaluate_additive_permissions(product_data, normalized_additives, result)

        # 5. Maximum levels for executable generic rules.
        # Included in the permission evaluator for now, so that a future
        # structured permission rule can use the same comparison machinery.

        # 6. Contaminants — current JSON has source pages but no executable
        # contaminant rules. Do not infer safety from absence of a rule.
        self._evaluate_contaminants(product_data, measurements, result)

        result["overall_status"] = self._overall_status(result)
        result["summary"] = self._summary(result)
        return result

    def resolve_additive(self, additive: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve an additive using INS first, then normalized name."""
        ins = normalize_ins(additive.get("ins"))
        declared_name = additive.get("declared_name")
        name_key = normalize_text(declared_name)

        rule = self._identity_by_ins.get(ins) if ins else None
        if rule is None and name_key:
            rule = self._identity_by_name.get(name_key)

        out = dict(additive)
        if rule is None:
            out.update({
                "normalized_name": None,
                "technical_function": None,
                "identity_status": DECISION_UNKNOWN,
                "source": {},
            })
            return out

        set_values = rule.get("then", {}).get("set", {})
        out.update({
            "normalized_name": set_values.get("additive.normalized_name"),
            "technical_function": set_values.get("additive.technical_function"),
            "identity_status": DECISION_COMPLIANT,
            "source": rule.get("source", {}),
        })
        return out

    # ---------- rule evaluation ----------

    def _evaluate_prohibitions(self, product_data: Dict[str, Any], result: Dict[str, Any]) -> None:
        rules = self.rules_by_type.get("PROHIBITION", [])
        if not rules:
            return
        for rule in rules:
            if self._when_matches(rule.get("when", {}), product_data):
                then = rule.get("then", {})
                status = then.get("decision", DECISION_NON_COMPLIANT)
                finding = Finding(
                    rule_id=rule.get("rule_id", ""),
                    rule_type=rule.get("rule_type", ""),
                    status=status,
                    message=then.get("message", "Explicit prohibition matched."),
                    source=rule.get("source", {}),
                    details={"rule": rule},
                )
                self._record_finding(result, finding)

    def _evaluate_additive_prohibitions(
        self,
        product_data: Dict[str, Any],
        additives: List[Dict[str, Any]],
        result: Dict[str, Any],
    ) -> None:
        """Per-additive bans (e.g. potassium bromate), matched by INS/name
        and optionally scoped to a category, using the same matcher as
        additive permissions so a ban can't silently fail to fire because
        the JSON `when` clause used a per-additive field."""
        category = self._category(product_data)
        for rule in self.rules_by_type.get("ADDITIVE_PROHIBITION", []):
            for additive in additives:
                if self._additive_matches(rule, additive, category):
                    then = rule.get("then", {})
                    self._record_finding(result, Finding(
                        rule_id=rule.get("rule_id", ""),
                        rule_type=rule.get("rule_type", ""),
                        status=then.get("decision", DECISION_NON_COMPLIANT),
                        message=then.get("message", "Additive is explicitly prohibited."),
                        source=rule.get("source", {}),
                        details={"additive": additive},
                    ))

    def _evaluate_product_standards(
        self,
        product_data: Dict[str, Any],
        measurements: List[Dict[str, Any]],
        result: Dict[str, Any],
    ) -> None:
        category = self._category(product_data)
        rules = self.rules_by_type.get("PRODUCT_STANDARD_NUMERIC", [])

        if not rules:
            return

        for rule in rules:
            when = rule.get("when", {})
            if when.get("field") == "food.category" and when.get("operator") == "REQUIRES_CATEGORY_RESOLUTION":
                self._defer(
                    result,
                    DECISION_UNKNOWN,
                    "Product-standard rule is not category-resolved in the current rule file.",
                    rule,
                )
                continue

            context = {"food": {"category": category}, "product": product_data.get("product") or {}}
            if not category or not self._when_matches(when, context):
                continue

            check = rule.get("check", {})
            measurement = self._find_measurement(measurements, check.get("field"))
            if measurement is None:
                self._defer(
                    result,
                    DECISION_NOT_EVALUABLE,
                    f"Required measurement '{check.get('field')}' was not supplied.",
                    rule,
                )
                continue

            passed = self._compare_measurement(measurement, check)
            if passed is None:
                self._defer(
                    result,
                    DECISION_UNKNOWN,
                    "Measurement could not be compared because its unit/value is unsupported.",
                    rule,
                    details={"measurement": measurement, "check": check},
                )
            elif passed:
                self._pass(result, rule, "Product-standard numeric requirement satisfied.")
            else:
                self._violate(
                    result,
                    rule,
                    "Product-standard numeric requirement failed.",
                    details={"measurement": measurement, "check": check},
                )

    def _evaluate_additive_permissions(
        self,
        product_data: Dict[str, Any],
        additives: List[Dict[str, Any]],
        result: Dict[str, Any],
    ) -> None:
        category = self._category(product_data)

        # Candidate rows are intentionally not executed as permission rules,
        # but are only surfaced when they actually concern one of the
        # additives on this label — otherwise every check() call would drag
        # in every unrelated candidate row from the whole rule file.
        for rule in self.rules_by_type.get("ADDITIVE_PERMISSION_CANDIDATE", []):
            for additive in additives:
                if self._additive_matches(rule, additive, category):
                    self._defer(
                        result,
                        DECISION_COLUMN,
                        "Additive table row is preserved but its food-product columns still require validation.",
                        rule,
                        details={"additive": additive},
                    )

        # Table lookup contracts are global caveats about coverage gaps in
        # the digitized rule set (e.g. "Appendix A category tables aren't
        # fully loaded yet"). If a rule scopes itself to a category via
        # `when`, only surface it for matching products; unscoped rules are
        # always surfaced since they describe engine-wide limitations.
        for rule in self.rules_by_type.get("ADDITIVE_TABLE", []):
            when = rule.get("when", {})
            if when and not self._when_matches(when, {"food": {"category": category}}):
                continue
            self._defer(
                result,
                DECISION_COLUMN,
                "Additive table requires validated column mapping before execution.",
                rule,
            )

        # Support future, fully structured ADDITIVE_PERMISSION rules.
        executable = self.rules_by_type.get("ADDITIVE_PERMISSION", [])
        for rule in executable:
            for additive in additives:
                if self._additive_matches(rule, additive, category):
                    self._execute_permission_rule(rule, additive, result)

    def _evaluate_contaminants(
        self,
        product_data: Dict[str, Any],
        measurements: List[Dict[str, Any]],
        result: Dict[str, Any],
    ) -> None:
        """
        Contaminant/residue limits in the source regulation are almost
        always category-specific (e.g. lead is 0.5 ppm in soft drinks but
        10 ppm in baking powder, with a catch-all "foods not specified"
        limit for anything else). Rules are grouped by their `check.field`
        (the contaminant/residue name); for each group we prefer a rule
        whose `when` clause matches this product's category, and fall back
        to an unscoped rule (the catch-all) only if no category-specific
        rule matched. If neither exists for this product's category, the
        parameter is silently skipped rather than guessed at.
        """
        rules = self.rules_by_type.get("CONTAMINANT_LIMIT", [])
        if not rules:
            return

        category = self._category(product_data)
        context = {"food": {"category": category}}

        by_field: Dict[str, List[Dict[str, Any]]] = {}
        for rule in rules:
            field = rule.get("check", {}).get("field")
            by_field.setdefault(field, []).append(rule)

        for field, field_rules in by_field.items():
            selected = None
            for rule in field_rules:
                when = rule.get("when")
                if when and self._when_matches(when, context):
                    selected = rule
                    break
            if selected is None:
                for rule in field_rules:
                    if not rule.get("when"):
                        selected = rule
                        break
            if selected is None:
                # Only category-scoped rows exist for this contaminant and
                # none matched this product's category -- nothing to check.
                continue

            rule = selected
            check = rule.get("check", {})
            measurement = self._find_measurement(measurements, field)
            if measurement is None:
                self._defer(
                    result,
                    DECISION_NOT_EVALUABLE,
                    "Contaminant limit requires a laboratory measurement that was not supplied.",
                    rule,
                )
                continue

            passed = self._compare_measurement(measurement, check)
            if passed is True:
                self._pass(result, rule, "Contaminant limit satisfied.")
            elif passed is False:
                self._violate(result, rule, "Contaminant limit exceeded.")
            else:
                self._defer(
                    result,
                    DECISION_UNKNOWN,
                    "Contaminant measurement could not be evaluated.",
                    rule,
                )

    # ---------- condition / comparison helpers ----------

    def _when_matches(self, when: Dict[str, Any], product_data: Dict[str, Any]) -> bool:
        if not when:
            return True

        if "all" in when:
            return all(self._when_matches(x, product_data) for x in when["all"])
        if "any" in when:
            return any(self._when_matches(x, product_data) for x in when["any"])

        field = when.get("field")
        operator = when.get("operator")
        expected = when.get("value")
        actual = self._get_field(product_data, field)

        if operator == "EQUALS":
            return normalize_text(actual) == normalize_text(expected)
        if operator == "IN":
            return normalize_text(actual) in {normalize_text(x) for x in (expected or [])}
        if operator == "NOT_EQUALS":
            return normalize_text(actual) != normalize_text(expected)
        if operator == "CONTAINS":
            return normalize_text(expected) in normalize_text(actual)
        if operator == "EXISTS":
            return actual is not None and actual != ""
        if operator == "MATCHES_TABLE_CATEGORY":
            # Table contracts are handled as deferred, never as an execution
            # claim, because their column mappings have not been validated.
            return False
        if operator == "REQUIRES_CATEGORY_RESOLUTION":
            return False
        return False

    @staticmethod
    def _get_field(data: Dict[str, Any], dotted: Optional[str]) -> Any:
        if not dotted:
            return None
        current: Any = data
        for part in dotted.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _additive_matches(self, rule: Dict[str, Any], additive: Dict[str, Any], category: str) -> bool:
        context = {
            "food": {"category": category},
            "additive": additive,
        }
        return self._when_matches(rule.get("when", {}), context)

    def _execute_permission_rule(
        self,
        rule: Dict[str, Any],
        additive: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        permission = rule.get("then", {})
        if permission.get("decision") in {DECISION_CONDITIONAL, DECISION_COMPLIANT}:
            maximum = permission.get("maximum_level")
            if maximum is not None:
                amount = _float(additive.get("amount"))
                unit = additive.get("unit")
                target_unit = maximum.get("unit")
                if amount is None or unit is None or target_unit is None:
                    self._defer(
                        result,
                        DECISION_UNKNOWN,
                        "Additive maximum level could not be evaluated from the supplied amount/unit.",
                        rule,
                    )
                    return

                converted = convert_amount(amount, unit, target_unit)
                if converted is None:
                    self._defer(
                        result,
                        DECISION_UNKNOWN,
                        "Unsupported concentration-unit conversion.",
                        rule,
                    )
                    return

                limit = float(maximum["value"])
                op = maximum.get("operator", "LTE")
                passed = self._compare_values(converted, op, limit)

                if passed:
                    self._pass(result, rule, "Additive permission and maximum level satisfied.")
                else:
                    self._violate(
                        result,
                        rule,
                        "Additive maximum level exceeded.",
                        details={
                            "additive": additive,
                            "detected_value": amount,
                            "detected_unit": unit,
                            "normalized_value": converted,
                            "limit": limit,
                            "limit_unit": target_unit,
                        },
                    )
            else:
                self._pass(result, rule, "Additive permission matched.")
        elif permission.get("decision") == DECISION_NON_COMPLIANT:
            self._violate(result, rule, "Additive is not permitted under the matched rule.")
        else:
            self._defer(
                result,
                DECISION_CONDITIONAL,
                "Matched additive rule has conditions that require evaluation.",
                rule,
            )

    def _compare_measurement(self, measurement: Dict[str, Any], check: Dict[str, Any]) -> Optional[bool]:
        value = _float(measurement.get("value"))
        if value is None:
            return None

        converted = convert_amount(value, measurement.get("unit"), check.get("unit"))
        if converted is None:
            return None

        return self._compare_values(converted, check.get("operator"), float(check.get("value")))

    @staticmethod
    def _compare_values(actual: float, operator: str, expected: float) -> bool:
        if operator == "LTE":
            return actual <= expected
        if operator == "LT":
            return actual < expected
        if operator == "GTE":
            return actual >= expected
        if operator == "GT":
            return actual > expected
        if operator == "EQUALS":
            return actual == expected
        raise ValueError(f"Unsupported comparison operator: {operator}")

    @staticmethod
    def _find_measurement(measurements: Iterable[Dict[str, Any]], parameter: Optional[str]) -> Optional[Dict[str, Any]]:
        if not parameter:
            return None
        target = normalize_text(parameter)
        for measurement in measurements:
            if normalize_text(measurement.get("parameter")) == target:
                return measurement
        return None

    @staticmethod
    def _category(product_data: Dict[str, Any]) -> str:
        return normalize_text((product_data.get("product") or {}).get("resolved_category"))

    # ---------- result helpers ----------

    def _validate_input(self, data: Dict[str, Any], result: Dict[str, Any]) -> None:
        if not isinstance(data.get("product"), dict):
            self._add_warning(result, DECISION_UNKNOWN, "Missing product object.")
        if not (data.get("product") or {}).get("resolved_category"):
            self._add_warning(
                result,
                DECISION_UNKNOWN,
                "No resolved food category supplied; category-specific rules cannot be executed safely.",
            )

    def _record_finding(self, result: Dict[str, Any], finding: Finding) -> None:
        if finding.status == DECISION_NON_COMPLIANT:
            result["violations"].append(finding.as_dict())
        elif finding.status in {DECISION_UNKNOWN, DECISION_COLUMN, DECISION_NOT_EVALUABLE, DECISION_CONDITIONAL}:
            result["deferred_checks"].append(finding.as_dict())
        else:
            result["passed_checks"].append(finding.as_dict())
        self._add_source(result, finding.source)

    def _pass(self, result: Dict[str, Any], rule: Dict[str, Any], message: str) -> None:
        self._record_finding(result, Finding(
            rule_id=rule.get("rule_id", ""),
            rule_type=rule.get("rule_type", ""),
            status=DECISION_COMPLIANT,
            message=message,
            source=rule.get("source", {}),
        ))

    def _violate(
        self,
        result: Dict[str, Any],
        rule: Dict[str, Any],
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._record_finding(result, Finding(
            rule_id=rule.get("rule_id", ""),
            rule_type=rule.get("rule_type", ""),
            status=DECISION_NON_COMPLIANT,
            message=message,
            source=rule.get("source", {}),
            details=details or {},
        ))

    def _defer(
        self,
        result: Dict[str, Any],
        status: str,
        message: str,
        rule: Dict[str, Any],
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._record_finding(result, Finding(
            rule_id=rule.get("rule_id", ""),
            rule_type=rule.get("rule_type", ""),
            status=status,
            message=message,
            source=rule.get("source", {}),
            details=details or {},
        ))

    @staticmethod
    def _add_warning(result: Dict[str, Any], status: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        result["warnings"].append({
            "status": status,
            "message": message,
            "details": details or {},
        })

    @staticmethod
    def _add_source(result: Dict[str, Any], source: Dict[str, Any]) -> None:
        if source and source not in result["sources"]:
            result["sources"].append(source)

    @staticmethod
    def _overall_status(result: Dict[str, Any]) -> str:
        if result["violations"]:
            return DECISION_NON_COMPLIANT

        statuses = {x["status"] for x in result["deferred_checks"]}
        if DECISION_COLUMN in statuses:
            return DECISION_COLUMN
        if DECISION_UNKNOWN in statuses or DECISION_NOT_EVALUABLE in statuses:
            return DECISION_UNKNOWN
        if DECISION_CONDITIONAL in statuses:
            return DECISION_CONDITIONAL
        if result["warnings"]:
            return DECISION_UNKNOWN
        return DECISION_COMPLIANT

    @staticmethod
    def _summary(result: Dict[str, Any]) -> Dict[str, int]:
        return {
            "violations": len(result["violations"]),
            "warnings": len(result["warnings"]),
            "passed_checks": len(result["passed_checks"]),
            "deferred_checks": len(result["deferred_checks"]),
            "sources": len(result["sources"]),
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the FSSAI regulation engine.")
    parser.add_argument("input_json", help="JSON file containing one product payload")
    parser.add_argument(
        "--rules",
        default="regulation/rules.json",
        help="Programmable rules JSON",
    )
    args = parser.parse_args()

    with open(args.input_json, "r", encoding="utf-8") as f:
        payload = json.load(f)

    engine = RegulationEngine(args.rules)
    print(json.dumps(engine.check(payload), indent=2, ensure_ascii=False))
