"""Custom exceptions for the analyzer."""


class FitnessAnalyzerError(Exception):
    """Base class for the errors this package raises on purpose."""


class InvalidRecordError(FitnessAnalyzerError, ValueError):
    """Raised when a CSV record cannot be accepted.

    A record can have several problems at once, so the error keeps a list of
    (field, reason) pairs. field is None for problems with the whole row, like
    the wrong number of columns.
    """

    def __init__(self, issues):
        if isinstance(issues, tuple):
            issues = [issues]
        self.issues = list(issues)
        super().__init__("; ".join(
            f"{field}: {reason}" if field else reason for field, reason in self.issues
        ))


class InvalidIdentifierError(InvalidRecordError):
    """Raised when an identifier has an invalid format."""

    def __init__(self, field, value, expected):
        self.field = field
        self.value = value
        super().__init__((field, f"{value!r} does not match the required format {expected}"))


class UnknownParticipantError(InvalidRecordError):
    """Raised when a session refers to a participant that is not in the profile file."""

    def __init__(self, participant_id):
        self.participant_id = participant_id
        super().__init__(("participant_id", f"unknown participant {participant_id!r}"))


class DataFileError(FitnessAnalyzerError):
    """Raised when a whole input file can't be used (missing, unreadable, wrong header)."""

    def __init__(self, path, reason):
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")
