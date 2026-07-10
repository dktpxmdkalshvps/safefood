"""
Shared reference tables for the SafeMeal cleansing engine.

This module is imported by BOTH `preprocess.py` (build-time integrity
flagging) and the runtime API (`app.sanitizer`), so the two stages can
never drift apart on what counts as "reliable" or "mistranslated".
"""
import re

# ---------------------------------------------------------------------------
# Region code (from filename / meta.store_region) -> Korean display name
# ---------------------------------------------------------------------------
REGION_LABELS = {
    "SL": "서울", "BS": "부산", "DG": "대구", "IN": "인천",
    "GJ": "광주", "DJ": "대전", "US": "울산", "GK": "경기",
    "KW": "강원", "CC": "충청", "JR": "전라", "KS": "경상",
    "JJ": "제주",
}

# ---------------------------------------------------------------------------
# store_type code (from meta.store_type) -> Korean display label
# Inferred from dominant food_type/food_subtype distribution per code.
# ---------------------------------------------------------------------------
STORE_TYPE_LABELS = {
    "BF01": "뷔페",
    "FF01": "패스트푸드",
    "IF01": "외국음식(멕시칸/양식)",
    "IF02": "외국음식(중식)",
    "IF03": "외국음식(일식)",
    "KF01": "한식",
    "KF02": "한식",
    "KF03": "한식/양식",
    "KF04": "한식",
    "KF05": "한식/주류",
    "KF06": "분식",
    "KF07": "한식",
}

# ---------------------------------------------------------------------------
# Pricing-tier / non-food rows disguised as menu items (e.g. "초등학생",
# "성인", "1인 기준"). These are system rate-card labels the original OCR
# pipeline mistakenly tagged as dishes. Negative lookaheads guard against
# false positives such as "아이스크림" containing "아이스".
# ---------------------------------------------------------------------------
TIER_PATTERN = re.compile(
    r"(초등학생|중학생|고등학생|미취학|유아(?!식)|소인|대인|성인(?!탕)|"
    r"어린이(?!날)|청소년|어른|아이(?!스)|공기밥\s*추가|추가\s*시|"
    r"봉사료|부가세|VAT|1인\s*기준|인당|콜키지)"
)

# ---------------------------------------------------------------------------
# Protein / seafood keyword table used to cross-check the `ko` name and
# `ingredients.ko` list against the translated free-text fields. If the
# translated text names a DIFFERENT protein than the Korean source, the
# row is flagged as a translation error (this catches the systematic
# "염통꼬치 -> Chicken Heart Skewers" style template-lookup bug found in
# the raw dataset).
# ---------------------------------------------------------------------------
PROTEIN_KEYWORDS = {
    "pork": {
        "ko": ["돼지고기", "돼지", "돈육", "삼겹", "목살", "항정살", "가브리살",
               "돈까스", "족발", "보쌈", "돈"],
        "en": ["pork", "ham", "bacon"],
        "ja": ["豚"],
        "zh_cn": ["猪"],
        "zh_tw": ["豬"],
    },
    "beef": {
        "ko": ["소고기", "쇠고기", "한우", "우삼겹", "차돌", "우육", "육회",
               "소갈비", "소염통", "우둔", "양지", "차돌박이"],
        "en": ["beef"],
        "ja": ["牛"],
        "zh_cn": ["牛"],
        "zh_tw": ["牛"],
    },
    "chicken": {
        "ko": ["닭고기", "닭", "치킨", "계육", "닭발", "닭갈비"],
        "en": ["chicken"],
        "ja": ["鶏", "チキン"],
        "zh_cn": ["鸡"],
        "zh_tw": ["雞"],
    },
    "shrimp": {
        "ko": ["새우"],
        "en": ["shrimp", "prawn"],
        "ja": ["エビ", "海老"],
        "zh_cn": ["虾"],
        "zh_tw": ["蝦"],
    },
    "squid": {
        "ko": ["오징어"],
        "en": ["squid"],
        "ja": ["イカ"],
        "zh_cn": ["鱿鱼"],
        "zh_tw": ["魷魚"],
    },
    "duck": {
        "ko": ["오리고기", "오리"],
        "en": ["duck"],
        "ja": ["鴨", "アヒル"],
        "zh_cn": ["鸭"],
        "zh_tw": ["鴨"],
    },
    "lamb": {
        "ko": ["양고기", "양갈비", "양꼬치", "양"],
        "en": ["lamb", "mutton"],
        "ja": ["羊", "ラム", "マトン"],
        "zh_cn": ["羊"],
        "zh_tw": ["羊"],
    },
    "fish": {
        "ko": ["생선", "물고기", "연어", "광어", "우럭", "참치", "고등어", "꽁치", "갈치", "조기", "명태", "동태", "황태", "노가리", "생선구이", "생선회"],
        "en": ["fish", "salmon", "tuna", "mackerel"],
        "ja": ["魚", "サーモン", "マグロ", "サバ"],
        "zh_cn": ["鱼", "三文鱼", "金枪鱼", "鲭鱼"],
        "zh_tw": ["魚", "鮭魚", "鮪魚", "鯖魚"],
    },
}

# Placeholder / internal-note leaks that sometimes survived into the
# production translation fields (e.g. "(后期)", "TBD", "확인필요").
PLACEHOLDER_LEAK_PATTERN = re.compile(
    r"[\(（][^)）]*(후기|后期|TBD|미정|추후|확인\s*필요|check)[^)）]*[\)）]",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Raw allergy token (as it appears in the source `allergy` list) -> one of
# Korea's 24 legally mandated food-allergen labeling categories, so the
# "avoid allergy" filter works across ko synonyms/variants consistently.
# ---------------------------------------------------------------------------
ALLERGEN_CATEGORY_MAP = {
    "돼지고기": "돼지고기", "돼지": "돼지고기", "돈육": "돼지고기",
    "쇠고기": "쇠고기", "소고기": "쇠고기", "한우": "쇠고기",
    "닭고기": "닭고기", "닭": "닭고기",
    "새우": "새우", "새우젓": "새우",
    "게": "게", "꽃게": "게",
    "굴": "조개류", "전복": "조개류", "홍합": "조개류", "조개": "조개류",
    "바지락": "조개류", "꼬막": "조개류", "가리비": "조개류",
    "오징어": "오징어", "낙지": "오징어", "문어": "오징어",
    "우유": "우유", "유제품": "우유", "치즈": "우유", "버터": "우유", "생크림": "우유",
    "계란": "난류", "달걀": "난류", "알류": "난류",
    "밀": "밀", "밀가루": "밀",
    "대두": "대두", "콩": "대두", "두부": "대두", "된장": "대두", "간장": "대두",
    "메밀": "메밀",
    "땅콩": "땅콩",
    "호두": "호두",
    "잣": "잣",
    "고등어": "고등어",
    "복숭아": "복숭아",
    "토마토": "토마토",
    "아황산류": "아황산류", "아황산함유": "아황산류",
    "참깨": "참깨", "깨": "참깨",
    "잣류": "잣",
}

ALL_ALLERGEN_CATEGORIES = sorted(set(ALLERGEN_CATEGORY_MAP.values()))


def normalize_allergen(raw: str) -> str:
    """Map a raw allergy token to its canonical legal category (fallback: itself)."""
    raw = raw.strip()
    return ALLERGEN_CATEGORY_MAP.get(raw, raw)
