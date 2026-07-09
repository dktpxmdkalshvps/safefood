# SafeMeal — 관광 음식메뉴판 데이터 정제 및 검색 서비스

AI Hub "관광 음식메뉴판 데이터"의 품질 결함(맵기 정보 100% 결측에 가까운 수치,
정식·뷔페류의 알레르기 성분 `[]` 오태깅, 다국어 번역 왜곡, 요금표 라벨 혼재)을
백엔드 단에서 방어하는 오프라인 검색 서비스입니다. 외부 LLM API나 벡터 DB 없이
SQLite FTS5 + 규칙 기반 엔진만으로 동작합니다.

## 빠른 시작

### 1) 로컬 실행

```bash
pip install -r requirements.txt
python preprocess.py          # data/labels/**.json -> data/processed/safemeal_pure.db
uvicorn app.main:app --reload --port 8000
```

브라우저에서 http://127.0.0.1:8000 접속. API 문서는 http://127.0.0.1:8000/docs.

### 2) Docker

```bash
docker compose up --build
```

이미지 빌드 시점에 `preprocess.py`가 실행되어 DB가 이미 구워진 채로 컨테이너가
시작되므로, 런타임에는 네트워크 접근이 전혀 필요 없습니다.

## 아키텍처

```
data/labels/**/*.json   (AI Hub 원본 라벨, 1000개 파일 · 13,980개 메뉴 어노테이션)
        │
        ▼  preprocess.py
data/processed/safemeal_pure.db
  ├─ menus            (정제된 메뉴 + 무결성 비트 플래그)
  ├─ menu_allergies    (24개 법정 알레르기 카테고리로 정규화)
  ├─ menus_fts          (FTS5, menu_id UNINDEXED)
  └─ excluded_rows        (요금표/좌석단가 등 격리된 비-메뉴 행 감사 로그)
        │
        ▼  FastAPI (app/main.py, app/routers/menus.py)
GET /api/v1/menus/search?q=&region=&avoid_allergies=&limit=&offset=
        │  검색 → 지역 필터 → 알레르기 회피 시 is_allergy_reliable=0 드랍
        │  → DataSanitizer.clean_translation (런타임 오역 교정)
        ▼
app/static/index.html  (Vanilla JS, 단일 정적 파일, 빌드 스텝 없음)
```

## 핵심 정제 로직

- **`app/lexicon.py`**: 지역/업종 코드 라벨, 요금표 행 판별 정규식, 단백질/알레르기
  키워드 사전, 24개 법정 알레르기 카테고리 정규화 테이블. `preprocess.py`와
  `app/sanitizer.py`가 공유하는 단일 소스.
- **`preprocess.py`**: 원본 JSON을 순회하며 메뉴별로
  - `is_spicy_known` — `spicy_level`이 `null`이 아닌지 (원본 데이터의 98%가 결측)
  - `is_allergy_reliable` / `allergy_unreliable_reason` — `allergy: []`인데
    `ingredients.ko`가 채워져 있으면 `mistagged_with_ingredients`(원천 오태깅),
    둘 다 비어 있으면 `no_data`(검증 불가)로 구분해 **둘 다 미검증으로 취급**
  - `is_translation_error` — 한국어 재료(`ingredients.ko`)가 암시하는
    단백질(돼지/소/닭/새우/오징어)과 번역문이 다른 단백질을 지칭하면 플래그
  를 계산하고, "초등학생"/"성인"/"1인 기준" 같은 좌석단가 행은 `excluded_rows`로
  격리해 `menus`에서 원천 제외합니다.
- **`app/sanitizer.py`의 `DataSanitizer.clean_translation`**: 검색 결과가
  반환되기 직전, 요청 단위로 번역 오류 필드를 교정합니다 (플레이스홀더 누출
  제거, 단백질 불일치 시 `{로마자 표기} ({재료 목록})` 형태로 안전하게 대체).
- **`app/routers/menus.py`의 검색 필터 레이어**: `avoid_allergies`가 지정되면
  해당 알레르기를 포함한 메뉴는 물론, **`is_allergy_reliable == 0`인 미검증
  메뉴도 함께 드랍**합니다 — "태그가 없다 = 안전하다"로 오독되지 않도록 하는
  것이 이 서비스의 핵심 안전장치입니다.

## API

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/v1/menus/search` | `q`, `region`, `avoid_allergies`(복수), `limit`, `offset` |
| GET | `/api/v1/menus/{menu_id}` | 메뉴 상세 |
| GET | `/api/v1/regions` | 지역 코드/이름/건수 |
| GET | `/api/v1/store-types` | 업종 코드/라벨/건수 |
| GET | `/api/v1/allergens` | 24개 법정 알레르기 카테고리별 태깅 건수 |
| GET | `/api/v1/stats` | 정제 통계 (결측률, 미검증률, 오역 교정 건수 등) |
| GET | `/api/v1/excluded-sample` | 요금표 오염으로 격리된 원본 행 샘플 (감사용) |

## 구현 메모

- 데모 UI는 빌드 스텝 없는 단일 정적 파일(`app/static/index.html`)로,
  Tailwind CDN 대신 인라인 유틸리티 CSS를 직접 작성해 인터넷이 차단된
  환경에서도 스타일이 100% 로드되도록 했습니다.
- `requirements.txt`의 버전(FastAPI 0.111.0 / Pydantic 2.7.4)은 `python:3.11-slim`
  기준 prebuilt wheel이 존재합니다. 로컬 개발 환경의 Python이 더 최신
  (예: 3.13+)이라면 해당 버전의 `pydantic-core`가 소스 빌드를 요구할 수 있으니,
  로컬 스모크 테스트만 할 경우 `pip install fastapi "uvicorn[standard]"`로
  최신 버전을 임시 설치해도 무방합니다 (Docker 이미지는 항상 pinned 버전 사용).
