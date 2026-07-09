"""
preprocess.py — build `data/processed/safemeal_pure.db` from the raw AI Hub
"관광 음식메뉴판 데이터" label JSON files under `data/labels/**`.

For every menu row this computes multi-bit integrity flags instead of
trusting the source data at face value:

  * is_spicy_known        -- spicy_level is not null (98%+ of the raw data
                              is null; the UI must show "정보 없음", never
                              silently imply "not spicy").
  * is_allergy_reliable    -- 0 when ingredients.ko is non-empty but
                              allergy is [] (the "침묵 오태깅" bug — an
                              empty list here means UNKNOWN, not "safe").
  * is_translation_error   -- 1 when a translated field names a protein
                              that contradicts the Korean source (see
                              app/sanitizer.py for the actual correction).

Rows that are really rate-card/pricing-tier labels (e.g. "초등학생",
"성인", "1인 기준") mistagged as dishes are quarantined into
`excluded_rows` instead of being inserted into `menus` at all.

Usage:  python preprocess.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import DB_PATH, LABELS_DIR, PROCESSED_DIR
from app.lexicon import REGION_LABELS, STORE_TYPE_LABELS, TIER_PATTERN, normalize_allergen
from app.sanitizer import DataSanitizer

SCHEMA = """
CREATE TABLE menus (
    menu_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file                TEXT NOT NULL,
    region_code                TEXT NOT NULL,
    region_name                TEXT NOT NULL,
    store_id                   TEXT,
    store_type                 TEXT,
    store_type_label           TEXT,
    food_type                  TEXT,
    food_subtype                TEXT,
    ko                         TEXT NOT NULL,
    en_roman                   TEXT,
    en                         TEXT,
    ja                         TEXT,
    zh_cn                      TEXT,
    zh_tw                      TEXT,
    price                      INTEGER,
    ingredients_ko              TEXT,
    ingredients_en              TEXT,
    ingredients_ja              TEXT,
    ingredients_zh_cn           TEXT,
    ingredients_zh_tw           TEXT,
    spicy_level                  INTEGER,
    is_spicy_known                INTEGER NOT NULL DEFAULT 0,
    is_allergy_reliable           INTEGER NOT NULL DEFAULT 1,
    allergy_unreliable_reason      TEXT,
    is_translation_error          INTEGER NOT NULL DEFAULT 0,
    translation_error_fields      TEXT
);

CREATE TABLE menu_allergies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_id             INTEGER NOT NULL REFERENCES menus(menu_id),
    allergen_raw        TEXT NOT NULL,
    allergen_category   TEXT NOT NULL
);

CREATE TABLE excluded_rows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file   TEXT NOT NULL,
    ko            TEXT,
    price         TEXT,
    reason        TEXT NOT NULL
);

CREATE VIRTUAL TABLE menus_fts USING fts5(
    menu_id UNINDEXED,
    ko, en, ja, zh_cn, zh_tw, ingredients_text
);

CREATE INDEX idx_menus_region ON menus(region_code);
CREATE INDEX idx_menus_store_type ON menus(store_type);
CREATE INDEX idx_menus_allergy_reliable ON menus(is_allergy_reliable);
CREATE INDEX idx_menu_allergies_category ON menu_allergies(allergen_category);
CREATE INDEX idx_menu_allergies_menu_id ON menu_allergies(menu_id);
"""


def parse_price(raw) -> int | None:
    if raw is None:
        return None
    digits = re.sub(r"[^0-9]", "", str(raw))
    return int(digits) if digits else None


def region_from_filename(name: str) -> str:
    return name.split("_", 1)[0]


def is_pricing_tier_row(ko: str, ingredients_ko: list[str]) -> bool:
    if not ko:
        return False
    return bool(TIER_PATTERN.search(ko)) and not ingredients_ko


def build() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    files = sorted(LABELS_DIR.glob("*/*.json"))
    if not files:
        print(f"No label files found under {LABELS_DIR}", file=sys.stderr)
        sys.exit(1)

    stats = {
        "files": 0,
        "raw_annotations": 0,
        "inserted_menus": 0,
        "excluded_pricing_tier": 0,
        "excluded_blank_name": 0,
        "spicy_known": 0,
        "allergy_unreliable": 0,
        "allergy_unreliable_mistagged_with_ingredients": 0,
        "allergy_unreliable_no_data": 0,
        "translation_error": 0,
    }

    for fp in files:
        stats["files"] += 1
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"skip unreadable file {fp}: {e}", file=sys.stderr)
            continue

        meta = payload.get("meta", {})
        region_code = meta.get("store_region") or region_from_filename(fp.name)
        region_name = REGION_LABELS.get(region_code, region_code)
        store_id = meta.get("store_id")
        store_type = meta.get("store_type")
        store_type_label = STORE_TYPE_LABELS.get(store_type, store_type or "기타")

        for ann in payload.get("annotations", []):
            info = ann.get("menu_information", {})
            stats["raw_annotations"] += 1

            ko = (info.get("ko") or "").strip()
            ingredients_ko = info.get("ingredients.ko") or []
            price_raw = info.get("price")

            if not ko:
                stats["excluded_blank_name"] += 1
                conn.execute(
                    "INSERT INTO excluded_rows (source_file, ko, price, reason) VALUES (?,?,?,?)",
                    (fp.name, ko, str(price_raw), "blank_name"),
                )
                continue

            if is_pricing_tier_row(ko, ingredients_ko):
                stats["excluded_pricing_tier"] += 1
                conn.execute(
                    "INSERT INTO excluded_rows (source_file, ko, price, reason) VALUES (?,?,?,?)",
                    (fp.name, ko, str(price_raw), "pricing_tier_row"),
                )
                continue

            ingredients_en = info.get("ingredients.en") or []
            ingredients_ja = info.get("ingredients.ja") or []
            ingredients_zh_cn = info.get("ingredients.zh_CN") or []
            ingredients_zh_tw = info.get("ingredients.zh_TW") or []
            allergy_raw = info.get("allergy") or []
            spicy_level = info.get("spicy_level")
            is_spicy_known = 1 if spicy_level is not None else 0

            # An empty allergy list is only trustworthy when nothing in the
            # dish could plausibly contain an allergen. Any row with an
            # empty allergy list is therefore treated as UNVERIFIED for
            # safety-filtering purposes; the reason distinguishes the
            # flagship AI-Hub bug (ingredients were captured but the
            # allergy step silently dropped them) from rows where no
            # structured data exists at all.
            if allergy_raw:
                is_allergy_reliable = 1
                allergy_unreliable_reason = None
            elif ingredients_ko:
                is_allergy_reliable = 0
                allergy_unreliable_reason = "mistagged_with_ingredients"
            else:
                is_allergy_reliable = 0
                allergy_unreliable_reason = "no_data"

            row_for_check = {
                "ko": ko,
                "en_roman": info.get("en.ROMAN"),
                "en": info.get("en"),
                "ja": info.get("ja"),
                "zh_cn": info.get("zh_CN"),
                "zh_tw": info.get("zh_TW"),
                "ingredients_ko": ingredients_ko,
            }
            bad_fields = DataSanitizer.detect_translation_errors(row_for_check)
            is_translation_error = 1 if bad_fields else 0

            if is_spicy_known:
                stats["spicy_known"] += 1
            if not is_allergy_reliable:
                stats["allergy_unreliable"] += 1
                stats[f"allergy_unreliable_{allergy_unreliable_reason}"] += 1
            if is_translation_error:
                stats["translation_error"] += 1

            cur = conn.execute(
                """INSERT INTO menus (
                    source_file, region_code, region_name, store_id, store_type,
                    store_type_label, food_type, food_subtype, ko, en_roman, en, ja,
                    zh_cn, zh_tw, price, ingredients_ko, ingredients_en, ingredients_ja,
                    ingredients_zh_cn, ingredients_zh_tw, spicy_level, is_spicy_known,
                    is_allergy_reliable, allergy_unreliable_reason,
                    is_translation_error, translation_error_fields
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    fp.name, region_code, region_name, store_id, store_type,
                    store_type_label, info.get("food_type"), info.get("food_subtype"),
                    ko, info.get("en.ROMAN"), info.get("en"), info.get("ja"),
                    info.get("zh_CN"), info.get("zh_TW"), parse_price(price_raw),
                    json.dumps(ingredients_ko, ensure_ascii=False),
                    json.dumps(ingredients_en, ensure_ascii=False),
                    json.dumps(ingredients_ja, ensure_ascii=False),
                    json.dumps(ingredients_zh_cn, ensure_ascii=False),
                    json.dumps(ingredients_zh_tw, ensure_ascii=False),
                    spicy_level, is_spicy_known, is_allergy_reliable,
                    allergy_unreliable_reason,
                    is_translation_error, json.dumps(bad_fields, ensure_ascii=False),
                ),
            )
            menu_id = cur.lastrowid
            stats["inserted_menus"] += 1

            for raw_allergen in allergy_raw:
                raw_allergen = raw_allergen.strip()
                if not raw_allergen:
                    continue
                conn.execute(
                    "INSERT INTO menu_allergies (menu_id, allergen_raw, allergen_category) VALUES (?,?,?)",
                    (menu_id, raw_allergen, normalize_allergen(raw_allergen)),
                )

            ingredients_text = " ".join(ingredients_ko + ingredients_en)
            conn.execute(
                "INSERT INTO menus_fts (menu_id, ko, en, ja, zh_cn, zh_tw, ingredients_text) VALUES (?,?,?,?,?,?,?)",
                (menu_id, ko, info.get("en") or "", info.get("ja") or "",
                 info.get("zh_CN") or "", info.get("zh_TW") or "", ingredients_text),
            )

    conn.commit()

    stats_row = json.dumps(stats, ensure_ascii=False, indent=2)
    (PROCESSED_DIR / "build_stats.json").write_text(stats_row, encoding="utf-8")
    conn.close()

    print("=== SafeMeal preprocess complete ===")
    print(stats_row)
    print(f"DB written to {DB_PATH}")


if __name__ == "__main__":
    build()
