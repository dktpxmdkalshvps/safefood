import pytest
from app.sanitizer import DataSanitizer

def test_detect_translation_errors_no_error():
    row = {
        "ko": "제육볶음",
        "ingredients_ko": ["돼지고기", "파"],
        "en": "Stir-fried pork",
        "ja": "豚肉炒め",
        "zh_cn": "炒猪肉",
        "zh_tw": "炒豬肉",
    }
    assert DataSanitizer.detect_translation_errors(row) == []

def test_detect_translation_errors_one_error():
    row = {
        "ko": "제육볶음",
        "ingredients_ko": ["돼지고기"],
        "en": "Stir-fried beef",  # lowercase "beef" to match dictionary
        "ja": "豚肉炒め",
        "zh_cn": "炒猪肉",
        "zh_tw": "炒豬肉",
    }
    assert DataSanitizer.detect_translation_errors(row) == ["en"]

def test_detect_translation_errors_multiple_errors():
    row = {
        "ko": "제육볶음",
        "ingredients_ko": ["돼지고기"],
        "en": "Stir-fried beef",  # "beef" triggers beef category
        "ja": "鶏肉炒め",      # "鶏" triggers chicken category
        "zh_cn": "炒猪肉",
        "zh_tw": "炒豬肉",
    }
    # Both "en" and "ja" contradict "pork"
    assert set(DataSanitizer.detect_translation_errors(row)) == {"en", "ja"}

def test_detect_translation_errors_missing_ko_category():
    # Neither ko nor ingredients_ko resolve to a single protein category
    row = {
        "ko": "샐러드",
        "ingredients_ko": ["상추", "토마토"],
        "en": "Salad with chicken", # Even if chicken is mentioned, ko category is unknown
    }
    assert DataSanitizer.detect_translation_errors(row) == []

def test_detect_translation_errors_ambiguous_ko_category():
    # Resolves to both pork and shrimp (ambiguous) -> returns []
    row = {
        "ko": "새우 돼지고기 볶음",
        "ingredients_ko": ["돼지고기", "새우"],
        "en": "Stir-fried beef",
    }
    assert DataSanitizer.detect_translation_errors(row) == []

def test_detect_translation_errors_missing_translations():
    row = {
        "ko": "제육볶음",
        "ingredients_ko": ["돼지고기"],
        # No translated fields provided
    }
    assert DataSanitizer.detect_translation_errors(row) == []

def test_detect_translation_errors_empty_string_translations():
    row = {
        "ko": "제육볶음",
        "ingredients_ko": ["돼지고기"],
        "en": "",
        "ja": None,
    }
    assert DataSanitizer.detect_translation_errors(row) == []

def test_detect_translation_errors_ko_name_only():
    row = {
        "ko": "삼겹살", # "삼겹" is in pork ko keywords
        "ingredients_ko": [],
        "en": "beef belly", # beef contradiction
    }
    assert DataSanitizer.detect_translation_errors(row) == ["en"]
