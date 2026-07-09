from pydantic import BaseModel, Field


class AllergenTag(BaseModel):
    raw: str
    category: str


class MenuItem(BaseModel):
    menu_id: int
    region_code: str
    region_name: str
    store_type: str | None = None
    store_type_label: str | None = None
    food_type: str | None = None
    food_subtype: str | None = None

    ko: str
    en_roman: str | None = None
    en: str | None = None
    ja: str | None = None
    zh_cn: str | None = None
    zh_tw: str | None = None

    price: int | None = None
    ingredients_ko: list[str] = Field(default_factory=list)
    allergens: list[AllergenTag] = Field(default_factory=list)

    spicy_level: int | None = None
    is_spicy_known: bool

    is_allergy_reliable: bool
    allergy_unreliable_reason: str | None = None
    is_translation_error: bool
    is_translation_corrected: bool
    corrected_fields: list[str] = Field(default_factory=list)


class CleansingStats(BaseModel):
    raw_annotations: int
    inserted_menus: int
    excluded_pricing_tier: int
    spicy_known: int
    spicy_known_pct: float
    allergy_unreliable: int
    allergy_unreliable_pct: float
    allergy_unreliable_mistagged_with_ingredients: int
    allergy_unreliable_no_data: int
    translation_error: int
    translation_error_pct: float


class SearchMeta(BaseModel):
    total_matched: int
    returned: int
    limit: int
    offset: int
    region: str | None = None
    query: str | None = None
    avoid_allergies: list[str] = Field(default_factory=list)
    dropped_for_allergy_safety: int = 0


class SearchResponse(BaseModel):
    meta: SearchMeta
    items: list[MenuItem]


class RegionOption(BaseModel):
    code: str
    name: str
    count: int


class StoreTypeOption(BaseModel):
    code: str
    label: str
    count: int
