import unittest
from pathlib import Path

from fitness_analyzer.exceptions import DataFileError, InvalidIdentifierError, InvalidRecordError
from fitness_analyzer.validation import (
    SESSION_COLUMNS,
    check_row_shape,
    to_number,
    validate_csv_filename,
    validate_participant_id,
    validate_session_id,
)


class IdentifierTests(unittest.TestCase):
    def test_valid_identifiers(self):
        self.assertEqual(validate_participant_id("P001"), "P001")
        self.assertEqual(validate_session_id("FIT-2026-001"), "FIT-2026-001")

    def test_invalid_participant_ids(self):
        for value in ["001", "P01", "P0001", "p001", " P001", "P001x", "S001", ""]:
            with self.subTest(value=value), self.assertRaises(InvalidIdentifierError):
                validate_participant_id(value)

    def test_invalid_session_ids(self):
        for value in ["FIT-26-102", "FIT-2026-01", "fit-2026-001", "FIT-2026-001-", "REC-2026-001"]:
            with self.subTest(value=value), self.assertRaises(InvalidIdentifierError):
                validate_session_id(value)

    def test_missing_identifier(self):
        with self.assertRaises(InvalidRecordError):
            validate_session_id(None)

    def test_identifier_error_is_value_error(self):
        with self.assertRaises(ValueError):
            validate_session_id("bad")

    def test_filename_validation(self):
        self.assertEqual(validate_csv_filename(Path("data/x.csv")), Path("data/x.csv"))
        with self.assertRaises(DataFileError):
            validate_csv_filename(Path("data/x.txt"))


class ConversionTests(unittest.TestCase):
    def test_to_number(self):
        self.assertEqual(to_number("68"), 68.0)
        self.assertEqual(to_number("3", int), 3)
        self.assertIsNone(to_number(None))

    def test_unconvertible_text_is_returned_unchanged(self):
        self.assertEqual(to_number("fast"), "fast")
        self.assertEqual(to_number("two", int), "two")
        self.assertEqual(to_number("1.5", int), "1.5")
        self.assertEqual(to_number("inf"), "inf")

    def test_wrong_row_length(self):
        with self.assertRaises(InvalidRecordError) as context:
            check_row_shape(["FIT-2026-001", "P001"], SESSION_COLUMNS)
        self.assertIn("expected 8 fields but found 2", str(context.exception))

    def test_empty_cells_become_none(self):
        row = ["FIT-2026-001", "P001", "0", " ", "1.2", "32.4", "", "0.9"]
        values = check_row_shape(row, SESSION_COLUMNS)
        self.assertIsNone(values["heart_rate"])
        self.assertIsNone(values["activity_level"])


if __name__ == "__main__":
    unittest.main()
