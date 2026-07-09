import json
import re
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from app.db import get_connection
from app.lexicon import ALL_ALLERGEN_CATEGORIES, REGION_LABELS, STORE_TYPE_LABELS
from app.sanitizer import DataSanitizer
from app.schemas import (
    CleansingStats,
    MenuItem,
    RegionOption,
    SearchMeta,
    SearchResponse,
    StoreTypeOption,
)

router = APIRouter(prefix="/api/v1", tags=["menus"])

_FTS_STRIP = re.compile(r'["*()]')


def _row_to_menu_item(row: dict, allergens: list[dict]) -> MenuItem:
    payload = {
        "ko": row["ko"],
        "en_roman": row["en_roman"],
        "en": row["en"],
        "ja": row["ja"],
        "zh_cn": row["zh_cn"],
        "zh_tw": row["zh_tw"],
        "ingredients_ko": json.loads(row["ingredients_ko"] or "[]"),
        "ingredients_en": json.loads(row["ingredients_en"] or "[]"),
        "ingredients_ja": json.loads(row["ingredients_ja"] or "[]"),
        "ingredients_zh_cn": json.loads(row["ingredients_zh_cn"] or "[]"),
        "ingredients_zh_tw": json.loads(row["ingredients_zh_tw"] or "[]"),
    }
    cleaned = DataSanitizer.clean_translation(payload)

    return MenuItem(
        menu_id=row["menu_id"],
        region_code=row["region_code"],
        region_name=row["region_name"],
        store_type=row["store_type"],
        store_type_label=row["store_type_label"],
        food_type=row["food_type"],
        food_subtype=row["food_subtype"],
        ko=row["ko"],
        en_roman=row["en_roman"],
        en=cleaned["en"],
        ja=cleaned["ja"],
        zh_cn=cleaned["zh_cn"],
        zh_tw=cleaned["zh_tw"],
        price=row["price"],
        ingredients_ko=payload["ingredients_ko"],
        allergens=allergens,
        spicy_level=row["spicy_level"],
        is_spicy_known=bool(row["is_spicy_known"]),
        is_allergy_reliable=bool(row["is_allergy_reliable"]),
        allergy_unreliable_reason=row["allergy_unreliable_reason"],
        is_translation_error=bool(row["is_translation_error"]),
        is_translation_corrected=cleaned["is_translation_corrected"],
        corrected_fields=cleaned["corrected_fields"],
    )


def _build_fts_match(q: str) -> str | None:
    tokens = [t for t in re.split(r"\s+", q.strip()) if t]
    safe_tokens = []
    for t in tokens:
        t = _FTS_STRIP.sub("", t)
        if t:
            safe_tokens.append(f'"{t}"')
    if not safe_tokens:
        return None
    return " OR ".join(safe_tokens)


@router.get("/menus/search", response_model=SearchResponse)
def search_menus(
    q: str | None = Query(None, description="자유 텍스트 검색어 (메뉴명/재료)"),
    region: str | None = Query(None, description="지역 코드, 예: SL, BS, JJ"),
    avoid_allergies: list[str] = Query(default_factory=list, description="회피할 알레르기 카테고리"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    with get_connection() as conn:
        where = []
        params: list = []

        if region:
            where.append("region_code = ?")
            params.append(region)

        if q:
            match_expr = _build_fts_match(q)
            if match_expr is None:
                return SearchResponse(
                    meta=SearchMeta(total_matched=0, returned=0, limit=limit, offset=offset,
                                     region=region, query=q, avoid_allergies=avoid_allergies),
                    items=[],
                )
            fts_rows = conn.execute(
                "SELECT menu_id FROM menus_fts WHERE menus_fts MATCH ?", (match_expr,)
            ).fetchall()
            fts_ids = [r["menu_id"] for r in fts_rows]
            if not fts_ids:
                return SearchResponse(
                    meta=SearchMeta(total_matched=0, returned=0, limit=limit, offset=offset,
                                     region=region, query=q, avoid_allergies=avoid_allergies),
                    items=[],
                )
            where.append(f"menu_id IN ({','.join('?' * len(fts_ids))})")
            params.extend(fts_ids)

        base_where = " AND ".join(where) if where else "1=1"
        candidates = conn.execute(
            f"SELECT menu_id, is_allergy_reliable FROM menus WHERE {base_where} ORDER BY menu_id",
            params,
        ).fetchall()

        dropped_for_safety = 0
        if avoid_allergies:
            placeholders = ",".join("?" * len(avoid_allergies))
            bad_rows = conn.execute(
                f"SELECT DISTINCT menu_id FROM menu_allergies WHERE allergen_category IN ({placeholders})",
                avoid_allergies,
            ).fetchall()
            bad_ids = {r["menu_id"] for r in bad_rows}

            final_ids = []
            for row in candidates:
                mid = row["menu_id"]
                if mid in bad_ids:
                    continue
                if not row["is_allergy_reliable"]:
                    dropped_for_safety += 1
                    continue
                final_ids.append(mid)
        else:
            final_ids = [row["menu_id"] for row in candidates]

        total_matched = len(final_ids)
        page_ids = final_ids[offset : offset + limit]

        items: list[MenuItem] = []
        if page_ids:
            placeholders = ",".join("?" * len(page_ids))
            rows = conn.execute(
                f"SELECT * FROM menus WHERE menu_id IN ({placeholders})", page_ids
            ).fetchall()
            rows_by_id = {r["menu_id"]: r for r in rows}

            allergen_rows = conn.execute(
                f"SELECT menu_id, allergen_raw, allergen_category FROM menu_allergies "
                f"WHERE menu_id IN ({placeholders})",
                page_ids,
            ).fetchall()
            allergens_by_menu: dict[int, list[dict]] = defaultdict(list)
            for a in allergen_rows:
                allergens_by_menu[a["menu_id"]].append(
                    {"raw": a["allergen_raw"], "category": a["allergen_category"]}
                )

            for mid in page_ids:
                items.append(_row_to_menu_item(rows_by_id[mid], allergens_by_menu.get(mid, [])))

        return SearchResponse(
            meta=SearchMeta(
                total_matched=total_matched,
                returned=len(items),
                limit=limit,
                offset=offset,
                region=region,
                query=q,
                avoid_allergies=avoid_allergies,
                dropped_for_allergy_safety=dropped_for_safety,
            ),
            items=items,
        )


@router.get("/menus/{menu_id}", response_model=MenuItem)
def get_menu(menu_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM menus WHERE menu_id = ?", (menu_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="menu not found")
        allergen_rows = conn.execute(
            "SELECT allergen_raw, allergen_category FROM menu_allergies WHERE menu_id = ?",
            (menu_id,),
        ).fetchall()
        allergens = [{"raw": a["allergen_raw"], "category": a["allergen_category"]} for a in allergen_rows]
        return _row_to_menu_item(row, allergens)


@router.get("/regions", response_model=list[RegionOption])
def list_regions():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT region_code, region_name, COUNT(*) AS cnt FROM menus "
            "GROUP BY region_code, region_name ORDER BY region_code"
        ).fetchall()
        return [RegionOption(code=r["region_code"], name=r["region_name"], count=r["cnt"]) for r in rows]


@router.get("/store-types", response_model=list[StoreTypeOption])
def list_store_types():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT store_type, store_type_label, COUNT(*) AS cnt FROM menus "
            "WHERE store_type IS NOT NULL GROUP BY store_type, store_type_label ORDER BY store_type"
        ).fetchall()
        return [StoreTypeOption(code=r["store_type"], label=r["store_type_label"], count=r["cnt"]) for r in rows]


@router.get("/allergens")
def list_allergens():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT allergen_category, COUNT(DISTINCT menu_id) AS cnt FROM menu_allergies "
            "GROUP BY allergen_category ORDER BY cnt DESC"
        ).fetchall()
        counts = {r["allergen_category"]: r["cnt"] for r in rows}
        return [{"category": c, "count": counts.get(c, 0)} for c in ALL_ALLERGEN_CATEGORIES]


@router.get("/stats", response_model=CleansingStats)
def cleansing_stats():
    with get_connection() as conn:
        raw_annotations = conn.execute("SELECT COUNT(*) AS c FROM excluded_rows").fetchone()["c"]
        inserted_menus = conn.execute("SELECT COUNT(*) AS c FROM menus").fetchone()["c"]
        raw_annotations += inserted_menus
        excluded_pricing_tier = conn.execute(
            "SELECT COUNT(*) AS c FROM excluded_rows WHERE reason = 'pricing_tier_row'"
        ).fetchone()["c"]
        spicy_known = conn.execute("SELECT COUNT(*) AS c FROM menus WHERE is_spicy_known = 1").fetchone()["c"]
        allergy_unreliable = conn.execute(
            "SELECT COUNT(*) AS c FROM menus WHERE is_allergy_reliable = 0"
        ).fetchone()["c"]
        allergy_unreliable_mistagged = conn.execute(
            "SELECT COUNT(*) AS c FROM menus WHERE allergy_unreliable_reason = 'mistagged_with_ingredients'"
        ).fetchone()["c"]
        allergy_unreliable_no_data = conn.execute(
            "SELECT COUNT(*) AS c FROM menus WHERE allergy_unreliable_reason = 'no_data'"
        ).fetchone()["c"]
        translation_error = conn.execute(
            "SELECT COUNT(*) AS c FROM menus WHERE is_translation_error = 1"
        ).fetchone()["c"]

        def pct(n: int) -> float:
            return round(100 * n / inserted_menus, 1) if inserted_menus else 0.0

        return CleansingStats(
            raw_annotations=raw_annotations,
            inserted_menus=inserted_menus,
            excluded_pricing_tier=excluded_pricing_tier,
            spicy_known=spicy_known,
            spicy_known_pct=pct(spicy_known),
            allergy_unreliable=allergy_unreliable,
            allergy_unreliable_pct=pct(allergy_unreliable),
            allergy_unreliable_mistagged_with_ingredients=allergy_unreliable_mistagged,
            allergy_unreliable_no_data=allergy_unreliable_no_data,
            translation_error=translation_error,
            translation_error_pct=pct(translation_error),
        )


@router.get("/excluded-sample")
def excluded_sample(limit: int = Query(20, ge=1, le=100)):
    """Transparency endpoint: sample of rows quarantined by preprocess.py
    (pricing-tier rows mistagged as dishes) — demonstrates the exclusion
    logic rather than hiding it."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT source_file, ko, price, reason FROM excluded_rows "
            "WHERE reason = 'pricing_tier_row' ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return rows
