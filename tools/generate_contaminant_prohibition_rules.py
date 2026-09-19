"""
Rule generator for:
  - Food Safety and Standards (Contaminants, Toxins and Residues) Regulations, 2011
      * 2.1.1 Metal contaminants (Lead, Copper, Arsenic, Tin, Zinc, Cadmium,
        Mercury, Methyl Mercury, Chromium, Nickel)
      * 2.2.1 Crop contaminants (mycotoxins) and naturally occurring toxins
      * 2.3.2 Antibiotic tolerance limits + zero-tolerance banned substances
        (seafood/fishery products)
  - Food Safety and Standards (Prohibition and Restrictions on Sales)
    Regulations, 2011
      * Numeric product standards and additive bans that are cleanly
        executable today (cream fat %, hexane residue limits, tobacco/
        nicotine, calcium carbide).

Deliberately NOT included in this pass (see conversation notes / backlog):
  - 2.3.1 insecticide residue table (149 rows) -- next batch
  - Qualitative/non-numeric prohibitions (added water in milk, kesari gram
    state-notification restrictions, mandatory-iodization-of-salt, etc.) --
    the engine doesn't yet have a rule type for "must contain X" mandates
    or free-text ingredient-adulteration checks, so encoding these now
    would just be guessing at a schema. Flagged as backlog instead.

Run this file to print the generated rules as a JSON array; merge_rules.py
merges the result into fssai_regulatory_programmable_rules.json.
"""

import json

CONTAMINANTS_SOURCE = {
    "regulation": "FSS (Contaminants, Toxins and Residues) Regulations, 2011",
}
PROHIBITION_SOURCE = {
    "regulation": "FSS (Prohibition and Restrictions on Sales) Regulations, 2011",
}

rules = []
_rule_ids_seen = set()


def add_rule(rule):
    rid = rule["rule_id"]
    if rid in _rule_ids_seen:
        raise ValueError(f"duplicate rule_id: {rid}")
    _rule_ids_seen.add(rid)
    rules.append(rule)


def contaminant_rule(rule_id, field, category, value, unit, section, note, operator="LTE"):
    """category=None means an unscoped/default rule (the catch-all row)."""
    rule = {
        "rule_id": rule_id,
        "rule_type": "CONTAMINANT_LIMIT",
        "check": {"field": field, "operator": operator, "value": value, "unit": unit},
        "source": {**CONTAMINANTS_SOURCE, "section": section, "note": note},
    }
    if category:
        rule["when"] = {"field": "food.category", "operator": "EQUALS", "value": category}
    add_rule(rule)


# ---------------------------------------------------------------------------
# 2.1.1 Metal contaminants
# ---------------------------------------------------------------------------

LEAD = [
    ("LEAD-CONCENTRATED-SOFT-DRINKS", "CONCENTRATED_SOFT_DRINKS", 0.5,
     "Concentrated soft drinks (excl. concentrates used in mfg of soft drinks)"),
    ("LEAD-FRUIT-VEG-JUICE", "FRUIT_VEGETABLE_JUICE", 1.0,
     "Fruit and vegetable juice incl. tomato juice, excl. lime/lemon juice"),
    ("LEAD-SOFT-DRINK-MFG-CONCENTRATES-LIME-LEMON", "SOFT_DRINK_MFG_CONCENTRATES_LIME_LEMON_JUICE", 2.0,
     "Concentrates used in mfg of soft drinks, lime juice and lemon juice"),
    ("LEAD-BAKING-POWDER", "BAKING_POWDER", 10.0, "Baking powder"),
    ("LEAD-EDIBLE-OILS-FATS", "EDIBLE_OILS_FATS", 0.5, "Edible oils and fats"),
    ("LEAD-INFANT-MILK-SUBSTITUTE", "INFANT_MILK_SUBSTITUTE_INFANT_FOOD", 0.2,
     "Infant milk substitute and infant foods"),
    ("LEAD-TURMERIC", "TURMERIC", 10.0, "Turmeric whole and powder"),
    ("LEAD-DEXTROSE-LOW-ASH-SUGAR", "DEXTROSE_AND_LOW_ASH_REFINED_SUGAR", 0.5,
     "Anhydrous dextrose/dextrose monohydrate, refined white sugar (sulphated ash <=0.03%)"),
    ("LEAD-ICE-CREAM", "ICE_CREAM_FROZEN_CONFECTIONS", 1.0, "Ice-cream, iced lollies and similar frozen confections"),
    ("LEAD-CANNED-FISH-MEAT-GELATIN", "CANNED_FISH_MEAT_GELATIN_EXTRACTS_DRIED_VEG", 5.0,
     "Canned fish, canned meats, edible gelatin, meat extracts, hydrolysed protein, dried/dehydrated vegetables (excl. onions)"),
    ("LEAD-SUGAR-HIGH-ASH-COLOURED", "SUGAR_HIGH_ASH_COLOURED", 5.0,
     "Sugar, sugar syrup, invert sugar, direct-consumption coloured sugars (sulphated ash > 1.0%)"),
    ("LEAD-RAW-SUGAR", "RAW_SUGAR", 5.0, "Raw sugars (except sold direct or for mfg other than refining)"),
    ("LEAD-MOLASSES-CARAMEL-GLUCOSE-STARCH", "MOLASSES_CARAMEL_GLUCOSE_STARCH_HIGH_ASH", 5.0,
     "Edible molasses, caramel (liquid/solid), glucose and starch conversion products (ash > 1.0%)"),
    ("LEAD-COCOA-POWDER", "COCOA_POWDER", 5.0, "Cocoa powder (on dry fat-free substance)"),
    ("LEAD-YEAST-PRODUCTS", "YEAST_PRODUCTS", 5.0, "Yeast and yeast products (on dry matter)"),
    ("LEAD-TEA-DEHYDRATED-ONION-HERBS-SEAWEED", "TEA_DEHYDRATED_ONION_DRIED_HERBS_SPICE_SEAWEED_DERIVATIVES", 10.0,
     "Tea, dehydrated onions, dried herbs/spices flavourings, alginic acid, alginates, agar, carrageenan and similar seaweed products (dry matter)"),
    ("LEAD-LIQUID-PECTIN-UNSPECIFIED-CHEMICALS", "LIQUID_PECTIN_UNSPECIFIED_CHEMICALS", 10.0,
     "Liquid pectin; chemicals not otherwise specified used as ingredients/processing aids"),
    ("LEAD-FOOD-COLOURING-NON-CARAMEL", "FOOD_COLOURING_NON_CARAMEL", 10.0, "Food colouring other than caramel (dry colouring matter)"),
    ("LEAD-SOLID-PECTIN", "SOLID_PECTIN", 50.0, "Solid pectin"),
    ("LEAD-HARD-BOILED-SUGAR-CONFECTIONERY", "HARD_BOILED_SUGAR_CONFECTIONERY", 2.0, "Hard boiled sugar confectionery"),
    ("LEAD-IRON-FORTIFIED-SALT", "IRON_FORTIFIED_SALT", 2.0, "Iron fortified common salt"),
    ("LEAD-PROCESSED-CANNED-MEAT", "PROCESSED_CANNED_MEAT_PRODUCTS", 2.5,
     "Corned beef, luncheon meat, cooked ham, chopped meat, canned chicken, canned mutton/goat meat and related products"),
    ("LEAD-VINEGAR", "VINEGAR_BREWED_SYNTHETIC", 0.0, "Brewed vinegar and synthetic vinegar (Nil)"),
    ("LEAD-DEFAULT", None, 2.53, "Foods not specified"),
]
for rid, cat, val, note in LEAD:
    contaminant_rule(rid, "lead", cat, val, "mg/kg", "2.1.1 Table item 1 (Lead)", note)

COPPER = [
    ("COPPER-SOFT-DRINKS-EXCL-CONCENTRATE-CARBONATED", "SOFT_DRINKS_EXCL_CONCENTRATE_CARBONATED", 7.0,
     "Soft drinks excluding concentrates and carbonated water"),
    ("COPPER-CARBONATED-WATER", "CARBONATED_WATER", 1.5, "Carbonated water"),
    ("COPPER-TODDY", "TODDY", 5.0, "Toddy"),
    ("COPPER-SOFT-DRINK-CONCENTRATES", "SOFT_DRINK_CONCENTRATES", 20.0, "Concentrates for soft drinks"),
    ("COPPER-CHICORY-COFFEE-FLAVOURINGS-PECTIN", "CHICORY_COFFEE_BEANS_FLAVOURINGS_LIQUID_PECTIN", 30.0,
     "Chicory dried/roasted, coffee beans, flavourings/pectin liquid"),
    ("COPPER-COLOURING-MATTER", "COLOURING_MATTER", 30.0, "Colouring matter (on dry colouring matter)"),
    ("COPPER-EDIBLE-GELATIN", "EDIBLE_GELATIN", 30.0, "Edible gelatin"),
    ("COPPER-TOMATO-KETCHUP", "TOMATO_KETCHUP", 50.0, "Tomato ketchup (on dried total solids)"),
    ("COPPER-YEAST-PRODUCTS", "YEAST_PRODUCTS", 60.0, "Yeast and yeast products (on dry matter)"),
    ("COPPER-COCOA-POWDER", "COCOA_POWDER", 70.0, "Cocoa powder (on fat-free substance)"),
    ("COPPER-TOMATO-PUREE-PASTE-POWDER-JUICE", "TOMATO_PUREE_PASTE_POWDER_JUICE_COCKTAIL", 100.0,
     "Tomato puree, paste, powder, juice and cocktails (on dried tomato solid)"),
    ("COPPER-TEA", "TEA", 150.0, "Tea"),
    ("COPPER-SOLID-PECTIN", "SOLID_PECTIN", 300.0, "Pectin, solid"),
    ("COPPER-HARD-BOILED-SUGAR-CONFECTIONERY", "HARD_BOILED_SUGAR_CONFECTIONERY", 5.0, "Hard boiled sugar confectionery"),
    ("COPPER-IRON-FORTIFIED-SALT", "IRON_FORTIFIED_SALT", 2.0, "Iron fortified common salt"),
    ("COPPER-TURMERIC", "TURMERIC", 5.0, "Turmeric whole and powder"),
    ("COPPER-FRUIT-JUICE-ORANGE-GRAPE-APPLE-TOMATO-PINEAPPLE-LEMON", "FRUIT_JUICE_ORANGE_GRAPE_APPLE_TOMATO_PINEAPPLE_LEMON", 5.0,
     "Juice of orange, grape, apple, tomato, pineapple and lemon"),
    ("COPPER-FRUIT-PULP-PRODUCTS", "FRUIT_PULP_PRODUCTS", 5.0, "Pulp and pulp products of any fruit"),
    ("COPPER-INFANT-MILK-SUBSTITUTE", "INFANT_MILK_SUBSTITUTE_INFANT_FOOD", 15.0,
     "Infant milk substitute and infant foods (max 15.0, but not less than 2.8)"),
    ("COPPER-VINEGAR", "VINEGAR_BREWED_SYNTHETIC", 0.0, "Brewed vinegar and synthetic vinegar (Nil)"),
    ("COPPER-CARAMEL", "CARAMEL", 20.0, "Caramel"),
    ("COPPER-DEFAULT", None, 30.0, "Foods not specified"),
]
for rid, cat, val, note in COPPER:
    contaminant_rule(rid, "copper", cat, val, "mg/kg", "2.1.1 Table item 2 (Copper)", note)

ARSENIC = [
    ("ARSENIC-MILK", "MILK", 0.1, "Milk"),
    ("ARSENIC-SOFT-DRINK-DILUTION-EXCL-CARBONATED", "SOFT_DRINK_DILUTION_EXCL_CARBONATED", 0.5,
     "Soft drink intended for consumption after dilution, except carbonated water"),
    ("ARSENIC-CARBONATED-WATER", "CARBONATED_WATER", 0.25, "Carbonated water"),
    ("ARSENIC-INFANT-MILK-SUBSTITUTE", "INFANT_MILK_SUBSTITUTE_INFANT_FOOD", 0.05, "Infant milk substitute and infant foods"),
    ("ARSENIC-TURMERIC", "TURMERIC", 0.1, "Turmeric whole and powder"),
    ("ARSENIC-FRUIT-JUICE-ORANGE-GRAPE-APPLE-TOMATO-PINEAPPLE-LEMON", "FRUIT_JUICE_ORANGE_GRAPE_APPLE_TOMATO_PINEAPPLE_LEMON", 0.2,
     "Juice of orange, grape, apple, tomato, pineapple and lemon"),
    ("ARSENIC-FRUIT-PULP-PRODUCTS", "FRUIT_PULP_PRODUCTS", 0.2, "Pulp and pulp products of any fruit"),
    ("ARSENIC-PRESERVATIVES-ANTIOXIDANTS-EMULSIFIERS-STABILISERS-SYNTHETIC-COLOURS",
     "PRESERVATIVES_ANTIOXIDANTS_EMULSIFIERS_STABILISERS_SYNTHETIC_COLOURS", 3.0,
     "Preservatives, anti-oxidants, emulsifying and stabilising agents and synthetic food colours (dry matter) -- limit on the additive itself, not the finished food"),
    ("ARSENIC-ICE-CREAM", "ICE_CREAM_FROZEN_CONFECTIONS", 0.5, "Ice-cream, iced lollies and similar frozen confections"),
    ("ARSENIC-DEHYDRATED-ONION-GELATIN-PECTIN", "DEHYDRATED_ONION_GELATIN_LIQUID_PECTIN", 2.0,
     "Dehydrated onions, edible gelatin, liquid pectin"),
    ("ARSENIC-CHICORY-DRIED-ROASTED", "CHICORY_DRIED_ROASTED", 4.0, "Chicory, dried or roasted"),
    ("ARSENIC-DRIED-HERBS-FININGS-SOLID-PECTIN-SPICES", "DRIED_HERBS_FININGS_SOLID_PECTIN_SPICES", 5.0,
     "Dried herbs, finings and clearing agents, solid pectin (all grades), spices"),
    ("ARSENIC-FOOD-COLOURING-NON-SYNTHETIC", "FOOD_COLOURING_NON_SYNTHETIC", 5.0, "Food colouring other than synthetic colouring (dry colouring matter)"),
    ("ARSENIC-HARD-BOILED-SUGAR-CONFECTIONERY", "HARD_BOILED_SUGAR_CONFECTIONERY", 1.0, "Hard boiled sugar confectionery"),
    ("ARSENIC-IRON-FORTIFIED-SALT", "IRON_FORTIFIED_SALT", 1.0, "Iron fortified common salt"),
    ("ARSENIC-VINEGAR", "VINEGAR_BREWED_SYNTHETIC", 0.1, "Brewed vinegar and synthetic vinegar"),
    ("ARSENIC-DEFAULT", None, 1.1, "Foods not specified"),
]
for rid, cat, val, note in ARSENIC:
    contaminant_rule(rid, "arsenic", cat, val, "mg/kg", "2.1.1 Table item 3 (Arsenic)", note)

TIN = [
    ("TIN-PROCESSED-CANNED-PRODUCTS", "PROCESSED_CANNED_PRODUCTS", 250.0, "Processed and canned products"),
    ("TIN-HARD-BOILED-SUGAR-CONFECTIONERY", "HARD_BOILED_SUGAR_CONFECTIONERY", 5.0, "Hard boiled sugar confectionery"),
    ("TIN-JAM-JELLY-MARMALADE", "JAM_JELLY_MARMALADE", 250.0, "Jam, jellies and marmalade"),
    ("TIN-FRUIT-JUICE-ORANGE-APPLE-TOMATO-PINEAPPLE-LEMON", "FRUIT_JUICE_ORANGE_APPLE_TOMATO_PINEAPPLE_LEMON", 250.0,
     "Juice of orange, apple, tomato, pineapple and lemon"),
    ("TIN-FRUIT-PULP-PRODUCTS", "FRUIT_PULP_PRODUCTS", 250.0, "Pulp and pulp products of any fruit"),
    ("TIN-INFANT-MILK-SUBSTITUTE", "INFANT_MILK_SUBSTITUTE_INFANT_FOOD", 5.0, "Infant milk substitute and infant foods"),
    ("TIN-TURMERIC", "TURMERIC", 0.0, "Turmeric whole and powder (Nil)"),
    ("TIN-PROCESSED-CANNED-MEAT", "PROCESSED_CANNED_MEAT_PRODUCTS", 250.0,
     "Corned beef, luncheon meat, cooked ham, chopped meat, canned chicken, canned mutton and goat meat"),
    ("TIN-DEFAULT", None, 250.0, "Foods not specified"),
]
for rid, cat, val, note in TIN:
    contaminant_rule(rid, "tin", cat, val, "mg/kg", "2.1.1 Table item 4 (Tin)", note)

ZINC = [
    ("ZINC-READY-TO-DRINK-BEVERAGES", "READY_TO_DRINK_BEVERAGES", 5.0, "Ready-to-drink beverages"),
    ("ZINC-FRUIT-JUICE-ORANGE-GRAPE-TOMATO-PINEAPPLE-LEMON", "FRUIT_JUICE_ORANGE_GRAPE_TOMATO_PINEAPPLE_LEMON", 5.0,
     "Juice of orange, grape, tomato, pineapple and lemon"),
    ("ZINC-FRUIT-PULP-PRODUCTS", "FRUIT_PULP_PRODUCTS", 5.0, "Pulp and pulp products of any fruit"),
    ("ZINC-INFANT-MILK-SUBSTITUTE", "INFANT_MILK_SUBSTITUTE_INFANT_FOOD", 50.0,
     "Infant milk substitute and infant foods (max 50.0, but not less than 25.0)"),
    ("ZINC-EDIBLE-GELATIN", "EDIBLE_GELATIN", 100.0, "Edible gelatin"),
    ("ZINC-TURMERIC", "TURMERIC", 25.0, "Turmeric whole and powder"),
    ("ZINC-FRUIT-VEG-PRODUCTS", "FRUIT_VEGETABLE_PRODUCTS", 50.0, "Fruit and vegetable products"),
    ("ZINC-HARD-BOILED-SUGAR-CONFECTIONERY", "HARD_BOILED_SUGAR_CONFECTIONERY", 5.0, "Hard boiled sugar confectionery"),
    ("ZINC-DEFAULT", None, 50.0, "Foods not specified"),
]
for rid, cat, val, note in ZINC:
    contaminant_rule(rid, "zinc", cat, val, "mg/kg", "2.1.1 Table item 5 (Zinc)", note)

CADMIUM = [
    ("CADMIUM-INFANT-MILK-SUBSTITUTE", "INFANT_MILK_SUBSTITUTE_INFANT_FOOD", 0.1, "Infant milk substitute and infant foods"),
    ("CADMIUM-TURMERIC", "TURMERIC", 0.1, "Turmeric whole and powder"),
    ("CADMIUM-DEFAULT", None, 1.5, "Other foods"),
]
for rid, cat, val, note in CADMIUM:
    contaminant_rule(rid, "cadmium", cat, val, "mg/kg", "2.1.1 Table item 6 (Cadmium)", note)

MERCURY = [
    ("MERCURY-FISH", "FISH", 0.5, "Fish"),
    ("MERCURY-DEFAULT", None, 1.0, "Other foods"),
]
for rid, cat, val, note in MERCURY:
    contaminant_rule(rid, "mercury", cat, val, "mg/kg", "2.1.1 Table item 7 (Mercury)", note)

contaminant_rule("METHYL-MERCURY-DEFAULT", "methyl mercury", None, 0.25, "mg/kg",
                  "2.1.1 Table item 8 (Methyl Mercury)", "All foods (calculated as the element)")

contaminant_rule("CHROMIUM-REFINED-SUGAR", "chromium", "REFINED_SUGAR", 20, "ppb",
                  "2.1.1 Table item 9 (Chromium)", "Refined sugar")

contaminant_rule("NICKEL-HYDROGENATED-INTERESTERIFIED-OILS-FATS", "nickel",
                  "HYDROGENATED_INTERESTERIFIED_VEGETABLE_OILS_FATS", 1.5, "mg/kg",
                  "2.1.1 Table item 10 (Nickel)",
                  "All hydrogenated, partially hydrogenated, interesterified vegetable oils and fats "
                  "(vanaspati, table margarine, bakery/industrial margarine, bakery shortening, fat spread, "
                  "partially hydrogenated soyabean oil)")

# ---------------------------------------------------------------------------
# 2.2.1 Crop contaminants (mycotoxins) and naturally occurring toxins
# ---------------------------------------------------------------------------

contaminant_rule("AFLATOXIN-DEFAULT", "aflatoxin", None, 30, "ug/kg", "2.2.1(1) item 1", "All articles of food")
contaminant_rule("AFLATOXIN-M1-MILK", "aflatoxin m1", "MILK", 0.5, "ug/kg", "2.2.1(1) item 2", "Milk")
contaminant_rule("PATULIN-APPLE-JUICE", "patulin", "APPLE_JUICE_AND_APPLE_JUICE_INGREDIENT_BEVERAGES", 50, "ug/kg",
                  "2.2.1(1) item 3", "Apple juice and apple juice ingredients in other beverages")
contaminant_rule("OCHRATOXIN-A-WHEAT-BARLEY-RYE", "ochratoxin a", "WHEAT_BARLEY_RYE", 20, "ug/kg",
                  "2.2.1(1) item 4", "Wheat, barley and rye")

contaminant_rule("AGARIC-ACID-DEFAULT", "agaric acid", None, 100, "ppm", "2.2.1(2) item 1",
                  "Any article of food (naturally occurring)")
contaminant_rule("HYDROCYANIC-ACID-DEFAULT", "hydrocyanic acid", None, 5, "ppm", "2.2.1(2) item 2",
                  "Any article of food (naturally occurring)")
contaminant_rule("HYPERICINE-DEFAULT", "hypericine", None, 1, "ppm", "2.2.1(2) item 3",
                  "Any article of food (naturally occurring)")
contaminant_rule("SAFFROLE-DEFAULT", "saffrole", None, 10, "ppm", "2.2.1(2) item 4",
                  "Any article of food (naturally occurring)")

# ---------------------------------------------------------------------------
# 2.3.2 Antibiotics and other pharmacologically active substances (seafood)
# ---------------------------------------------------------------------------

SEAFOOD = "SEAFOOD_SHRIMP_PRAWN_FISH_FISHERY_PRODUCTS"

ANTIBIOTIC_TOLERANCE = [
    ("TETRACYCLINE-SEAFOOD", "tetracycline", 0.1),
    ("OXYTETRACYCLINE-SEAFOOD", "oxytetracycline", 0.1),
    ("TRIMETHOPRIM-SEAFOOD", "trimethoprim", 0.05),
    ("OXOLINIC-ACID-SEAFOOD", "oxolinic acid", 0.3),
]
for rid, field, val in ANTIBIOTIC_TOLERANCE:
    contaminant_rule(rid, field, SEAFOOD, val, "mg/kg", "2.3.2(1)",
                      "Sea foods including shrimps, prawns or any other variety of fish and fishery products")

BANNED_IN_SEAFOOD = [
    "furaltadone", "furazolidone", "furylfuramide", "nifuratel", "nifuroxime",
    "nifurprazine", "nitrofurantoin", "nitrofurazone", "chloramphenicol",
    "neomycin", "nalidixic acid", "sulphamethoxazole",
    "aristolochia spp and preparations thereof", "chloroform",
    "chloropromazine", "cholchicine", "dapsone", "dimetridazole",
    "metronidazole", "ronidazole", "ipronidazole", "other nitroimidazoles",
    "clenbuterol", "diethylstibestrol (des)", "fluoroquinolones", "glycopeptides",
]
for substance in BANNED_IN_SEAFOOD:
    rid = "BAN-SEAFOOD-" + substance.upper().replace(" ", "-").replace("(", "").replace(")", "")
    contaminant_rule(rid, substance, SEAFOOD, 0.0, "mg/kg", "2.3.2(2)",
                      "Use prohibited in any unit processing sea foods including shrimps, prawns or any "
                      "other variety of fish and fishery products (zero-tolerance residue).", operator="LTE")
# Note: "All Nitrofurans" (the class heading) and the "sulfonamide drugs except
# approved ..." exception aren't single measurable substance names -- flagged
# as backlog rather than force-fit into a single CONTAMINANT_LIMIT row.

# ---------------------------------------------------------------------------
# Prohibition Regulations -- numeric standards and clean additive bans
# ---------------------------------------------------------------------------

add_rule({
    "rule_id": "STANDARD-CREAM-MIN-MILK-FAT",
    "rule_type": "PRODUCT_STANDARD_NUMERIC",
    "when": {"field": "food.category", "operator": "EQUALS", "value": "CREAM"},
    "check": {"field": "milk fat", "operator": "GTE", "value": 25.0, "unit": "%"},
    "source": {**PROHIBITION_SOURCE, "section": "2.1.1(1)",
               "note": "Cream must be prepared exclusively from milk and contain not less than 25% milk fat."},
})

HEXANE_LIMITS = [
    ("HEXANE-RESIDUE-COCOA-BUTTER-SOLVENT-EXTRACTED", "COCOA_BUTTER_SOLVENT_EXTRACTED", 5.0,
     "Refined solvent-extracted cocoa butter"),
    ("HEXANE-RESIDUE-SOLVENT-EXTRACTED-OILS-FATS", "SOLVENT_EXTRACTED_OILS_FATS", 5.0,
     "Refined solvent-extracted oils and fats"),
    ("HEXANE-RESIDUE-SOLVENT-EXTRACTED-SOYA-FLOUR", "SOLVENT_EXTRACTED_EDIBLE_SOYA_FLOUR", 10.0,
     "Solvent-extracted edible soya flour"),
]
for rid, cat, val, note in HEXANE_LIMITS:
    add_rule({
        "rule_id": rid,
        "rule_type": "CONTAMINANT_LIMIT",
        "when": {"field": "food.category", "operator": "EQUALS", "value": cat},
        "check": {"field": "hexane residue", "operator": "LTE", "value": val, "unit": "mg/kg"},
        "source": {**PROHIBITION_SOURCE, "section": "2.3.15(6)",
                   "note": f"{note}. Only n-Hexane (food grade) may be used as solvent for extraction."},
    })

BANNED_INGREDIENTS = [
    ("PROHIBITION-TOBACCO", ["tobacco"], "Tobacco shall not be used as an ingredient in any food product.", "2.3.4"),
    ("PROHIBITION-NICOTINE", ["nicotine"], "Nicotine shall not be used as an ingredient in any food product.", "2.3.4"),
    ("PROHIBITION-CALCIUM-CARBIDE", ["calcium carbide", "carbide gas"],
     "Carbide gas (calcium carbide) shall not be used to artificially ripen fruit.", "2.3.5"),
]
for rid, names, message, section in BANNED_INGREDIENTS:
    add_rule({
        "rule_id": rid,
        "rule_type": "ADDITIVE_PROHIBITION",
        "when": {"field": "additive.declared_name", "operator": "IN", "value": names},
        "then": {"decision": "NON_COMPLIANT", "message": message},
        "source": {**PROHIBITION_SOURCE, "section": section},
    })

if __name__ == "__main__":
    print(json.dumps(rules, indent=2, ensure_ascii=False))
    import sys
    print(f"\n# generated {len(rules)} rules", file=sys.stderr)
