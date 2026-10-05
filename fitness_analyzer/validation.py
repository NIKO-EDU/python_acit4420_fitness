"""Identifier checks and turning CSV text into Python values.

Regular expressions are only used for identifiers and file names. The range
checks for the measurements are in the RangeRule classes in models.py.
"""

import math
import re

from .exceptions import DataFileError, InvalidIdentifierError, InvalidRecordError

PARTICIPANT_ID_PATTERN = re.compile(r"P\d{3}")
SESSION_ID_PATTERN = re.compile(r"FIT-\d{4}-\d{3}")
CSV_FILENAME_PATTERN = re.compile(r"[\w\-. ]+\.csv", re.IGNORECASE)

PARTICIPANT_COLUMNS = ("participant_id", "name", "baseline_heart_rate",
                       "baseline_skin_response", "baseline_temperature")
SESSION_COLUMNS = ("session_id", "participant_id", "timestamp", "heart_rate",
                   "skin_response", "temperature", "activity_level", "signal_quality")


def _validate_identifier(field, value, pattern, expected):
    if value is None:
        raise InvalidRecordError((field, "required value is missing"))
    if not pattern.fullmatch(value):
        raise InvalidIdentifierError(field, value, expected)
    return value


def validate_participant_id(value):
    return _validate_identifier("participant_id", value, PARTICIPANT_ID_PATTERN,
                                "P followed by three digits (e.g. P001)")


def validate_session_id(value):
    return _validate_identifier("session_id", value, SESSION_ID_PATTERN,
                                "FIT-YYYY-NNN (e.g. FIT-2026-001)")


def validate_csv_filename(path):
    if not CSV_FILENAME_PATTERN.fullmatch(path.name):
        raise DataFileError(path, "expected a file name ending in .csv")
    return path


def check_row_shape(row, columns):
    """Return the row as {column: text}, with empty cells as None.

    Raises InvalidRecordError if the row has the wrong number of fields.
    """
    if len(row) != len(columns):
        raise InvalidRecordError((None, f"expected {len(columns)} fields but found {len(row)}"))
    return {column: (cell.strip() or None) for column, cell in zip(columns, row)}


def to_number(raw, number_type=float):
    """Convert CSV text to a number.

    Text that can't be converted comes back unchanged, and the RangeRule then
    rejects it as "not a number". That way all the problems in a row get
    reported together, and not just the first conversion error.
    """
    if raw is None:
        return None
    try:
        value = number_type(raw)
    except ValueError:
        return raw
    if isinstance(value, float) and math.isinf(value):
        return raw
    return value
