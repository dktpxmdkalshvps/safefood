from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LABELS_DIR = DATA_DIR / "labels"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = PROCESSED_DIR / "safemeal_pure.db"
STATIC_DIR = BASE_DIR / "app" / "static"
