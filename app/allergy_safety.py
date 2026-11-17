"""Conservative checks for inconsistencies in unverified source allergy tags.

Passing these checks is NOT proof that a dish is allergen-free.
"""
from app.lexicon import ALLERGEN_CATEGORY_MAP, normalize_allergen

# Match unambiguous ingredient names only; avoid substring matches such as
# '밀' inside unrelated Korean words. Unknown ingredients are not certified.
INGREDIENT_ALIASES = {
    "우유": "우유", "치즈": "우유", "버터": "우유",
    "계란": "난류", "달걀": "난류",
    "밀가루": "밀", "메밀": "메밀",
    "땅콩": "땅콩", "호두": "호두", "잣": "잣",
    "두부": "대두", "된장": "대두", "간장": "대두",
    "새우": "새우", "새우젓": "새우", "꽃게": "게",
    "오징어": "오징어", "돼지고기": "돼지고기",
    "소고기": "쇠고기", "쇠고기": "쇠고기",
    "닭고기": "닭고기", "고등어": "고등어",
    "복숭아": "복숭아", "토마토": "토마토",
}


def assess_allergy(raw_tags, ingredients, menu_name=""):
    """Return (reliable, reason). Never infer safety from an empty tag list."""
    if not isinstance(raw_tags, list) or not isinstance(ingredients, list):
        return 0, "invalid_allergy_data"
    if not raw_tags:
        return (0, "mistagged_with_ingredients" if ingredients else "no_data")
    if any(not isinstance(tag, str) or not tag.strip() for tag in raw_tags):
        return 0, "invalid_allergy_data"
    categories = {normalize_allergen(tag) for tag in raw_tags}
    if any(category not in ALLERGEN_CATEGORY_MAP.values() for category in categories):
        return 0, "unknown_allergen_category"
    for ingredient in ingredients:
        if not isinstance(ingredient, str):
            return 0, "invalid_allergy_data"
        inferred = INGREDIENT_ALIASES.get(ingredient.strip())
        if inferred and inferred not in categories:
            return 0, "ingredient_allergen_mismatch"
    # Source tags are internally consistent, but not independently certified.
    return 1, None
