import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.allergy_safety import assess_allergy
import preprocess


class AllergySafetyTests(unittest.TestCase):
    def test_empty_tags_are_unverified(self):
        self.assertEqual(assess_allergy([], ["우유"]), (0, "mistagged_with_ingredients"))
        self.assertEqual(assess_allergy([], []), (0, "no_data"))

    def test_missing_ingredient_tag_is_unverified(self):
        self.assertEqual(
            assess_allergy(["밀"], ["우유"]), (0, "ingredient_allergen_mismatch")
        )

    def test_unknown_and_invalid_tags_are_unverified(self):
        self.assertEqual(
            assess_allergy(["unrecognized"], []), (0, "unknown_allergen_category")
        )
        self.assertEqual(assess_allergy([None], []), (0, "invalid_allergy_data"))

    def test_consistent_tags_not_rejected(self):
        self.assertEqual(assess_allergy(["우유"], ["치즈"]), (1, None))


class AtomicBuildTests(unittest.TestCase):
    def test_corrupt_input_preserves_existing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labels = root / "labels"
            (labels / "SL").mkdir(parents=True)
            (labels / "SL" / "bad.json").write_text("{broken", encoding="utf-8")
            processed = root / "processed"
            processed.mkdir()
            db = processed / "safemeal_pure.db"
            db.write_bytes(b"existing-db")
            with (
                patch.object(preprocess, "LABELS_DIR", labels),
                patch.object(preprocess, "PROCESSED_DIR", processed),
                patch.object(preprocess, "DB_PATH", db),
            ):
                with self.assertRaises(ValueError):
                    preprocess.build()
            self.assertEqual(db.read_bytes(), b"existing-db")
            self.assertEqual(list(processed.glob(".safemeal-*.db")), [])

    def test_empty_input_preserves_existing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labels = root / "labels"
            labels.mkdir()
            processed = root / "processed"
            processed.mkdir()
            db = processed / "safemeal_pure.db"
            db.write_bytes(b"existing-db")
            with (
                patch.object(preprocess, "LABELS_DIR", labels),
                patch.object(preprocess, "PROCESSED_DIR", processed),
                patch.object(preprocess, "DB_PATH", db),
            ):
                with self.assertRaises(RuntimeError):
                    preprocess.build()
            self.assertEqual(db.read_bytes(), b"existing-db")


if __name__ == "__main__":
    unittest.main()
