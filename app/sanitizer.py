"""
DataSanitizer — the runtime translation-correction stage.

`preprocess.py` bakes an `is_translation_error` bit into the database so the
API can index/filter cheaply. `DataSanitizer.clean_translation` performs the
actual text-level correction on the small result set a request returns,
right before it is serialized to the client (see the "Filter layer" in the
project spec). Keeping correction at request time (instead of only at
build time) means the same logic can be re-run against re-scraped data
without a full reprocessing pass.
"""
from __future__ import annotations

from typing import Any

from app.lexicon import PLACEHOLDER_LEAK_PATTERN, PROTEIN_KEYWORDS

_LANG_FIELDS = ["en", "ja", "zh_cn", "zh_tw"]


def detect_ko_category(ko_name: str, ingredients_ko: list[str]) -> str | None:
    """Infer the single protein/seafood category implied by the Korean source.

    Returns None when no keyword matches, or when more than one distinct
    category matches (ambiguous — e.g. a dish containing both pork and
    shrimp), since a translation check can't safely fire in that case.
    """
    haystacks = list(ingredients_ko) + [ko_name or ""]
    found = set()
    for category, kw in PROTEIN_KEYWORDS.items():
        if any(any(k in h for k in kw["ko"]) for h in haystacks):
            found.add(category)
    if len(found) == 1:
        return next(iter(found))
    return None


def _find_wrong_category(text: str, lang: str, ko_category: str) -> str | None:
    if not text:
        return None
    for category, kw in PROTEIN_KEYWORDS.items():
        if category == ko_category:
            continue
        if any(k in text for k in kw[lang]):
            return category
    return None


class DataSanitizer:
    """Static-only helper — no instance state, safe to call per-row per-request."""

    @staticmethod
    def detect_translation_errors(row: dict[str, Any]) -> list[str]:
        """Return the list of language fields ("en","ja","zh_cn","zh_tw")
        whose free text names a protein that contradicts the Korean source."""
        ko_category = detect_ko_category(row.get("ko", ""), row.get("ingredients_ko") or [])
        if ko_category is None:
            return []
        bad_fields = []
        for lang in _LANG_FIELDS:
            wrong = _find_wrong_category(row.get(lang, "") or "", lang, ko_category)
            if wrong is not None:
                bad_fields.append(lang)
        return bad_fields

    @staticmethod
    def clean_translation(row: dict[str, Any]) -> dict[str, Any]:
        """Return a COPY of `row` with mistranslated / placeholder-leaked
        language fields corrected, plus a `corrected_fields` list describing
        what changed (used by the frontend to light up the correction badge).
        """
        out = dict(row)
        corrected_fields: list[str] = []

        # 1) strip leaked internal placeholders, e.g. "(后期)" / "(TBD)"
        for lang in _LANG_FIELDS:
            text = out.get(lang) or ""
            stripped = PLACEHOLDER_LEAK_PATTERN.sub("", text).strip()
            if stripped != text:
                out[lang] = stripped
                corrected_fields.append(lang)

        # 2) fix protein/seafood mismatches against the Korean source
        ko_category = detect_ko_category(out.get("ko", ""), out.get("ingredients_ko") or [])
        if ko_category is not None:
            roman = out.get("en_roman") or out.get("ko", "")
            for lang in _LANG_FIELDS:
                text = out.get(lang) or ""
                wrong = _find_wrong_category(text, lang, ko_category)
                if wrong is None:
                    continue
                ingredients_key = f"ingredients_{lang}"
                ingredients = out.get(ingredients_key) or []
                if ingredients:
                    fallback = f"{roman} ({', '.join(ingredients)})"
                else:
                    fallback = roman
                out[lang] = fallback
                if lang not in corrected_fields:
                    corrected_fields.append(lang)

        out["corrected_fields"] = corrected_fields
        out["is_translation_corrected"] = len(corrected_fields) > 0
        return out
