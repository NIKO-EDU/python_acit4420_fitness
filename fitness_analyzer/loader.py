"""Reading the CSV files and turning the rows into objects."""

import csv
from dataclasses import dataclass

from .exceptions import DataFileError, InvalidRecordError, UnknownParticipantError
from .models import Observation, Participant, ReferenceProfile, TrainingSession
from .validation import (
    PARTICIPANT_COLUMNS,
    SESSION_COLUMNS,
    check_row_shape,
    to_number,
    validate_csv_filename,
    validate_participant_id,
    validate_session_id,
)


@dataclass(frozen=True)
class RejectedRecord:
    """A CSV row that was not accepted, with every reason why."""

    source_file: str
    row_number: int
    issues: list
    raw_row: list


def read_csv_rows(path, expected_columns):
    """Return [(line_number, row), ...] for the data rows in a CSV file.

    The whole file is read at once, so any problem with the file itself comes
    out as one DataFileError with the file name in it.
    """
    validate_csv_filename(path)
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header is None:
                raise DataFileError(path, "file is empty (no header row)")
            header = [name.strip() for name in header]
            if tuple(header) != expected_columns:
                raise DataFileError(path, f"unexpected header {header}; expected {list(expected_columns)}")
            # csv.reader gives [] for blank lines, so those are skipped
            return [(reader.line_num, row) for row in reader if row]
    except FileNotFoundError:
        raise DataFileError(path, "file not found") from None
    except PermissionError:
        raise DataFileError(path, "permission denied when opening the file") from None
    except IsADirectoryError:
        raise DataFileError(path, "path is a directory, not a file") from None
    except UnicodeDecodeError as error:
        raise DataFileError(path, f"file is not valid UTF-8 ({error.reason} at byte {error.start})") from None
    except csv.Error as error:
        raise DataFileError(path, f"malformed CSV: {error}") from None


class DataLoader:
    """Loads participants and sessions and keeps track of every rejected row."""

    def __init__(self):
        self.participants = {}
        self.sessions = {}
        self.rejected = []
        self.accepted_rows = 0

    def load_participants(self, path):
        """Load the profile file. Raises DataFileError if the file can't be used at all."""
        for line_number, row in read_csv_rows(path, PARTICIPANT_COLUMNS):
            try:
                participant = self._parse_participant(row)
            except InvalidRecordError as error:
                self._reject(path, line_number, error.issues, row)
                continue
            self.participants[participant.participant_id] = participant
        if not self.participants:
            raise DataFileError(path, "no valid participant profiles were found")
        return self.participants

    def load_sessions(self, path):
        """Load one session file into self.sessions and return how many rows were accepted."""
        accepted = 0
        for line_number, row in read_csv_rows(path, SESSION_COLUMNS):
            try:
                self._add_session_row(row, path.name, line_number)
            except InvalidRecordError as error:
                self._reject(path, line_number, error.issues, row)
                continue
            accepted += 1
        self.accepted_rows += accepted
        return accepted

    def _reject(self, path, line_number, issues, row):
        self.rejected.append(RejectedRecord(path.name, line_number, issues, list(row)))

    def _parse_participant(self, row):
        values = check_row_shape(row, PARTICIPANT_COLUMNS)
        issues = []
        participant_id = values["participant_id"]
        try:
            validate_participant_id(participant_id)
            if participant_id in self.participants:
                issues.append(("participant_id", f"duplicate participant {participant_id}"))
        except InvalidRecordError as error:
            issues.extend(error.issues)
        if values["name"] is None:
            issues.append(("name", "required value is missing"))
        profile = {field: to_number(values[field]) for field in PARTICIPANT_COLUMNS[2:]}
        try:
            reference = ReferenceProfile.from_profile(profile)
        except InvalidRecordError as error:
            issues.extend(error.issues)
        if issues:
            raise InvalidRecordError(issues)
        return Participant(participant_id, reference, name=values["name"])

    def _add_session_row(self, row, source_file, line_number):
        values = check_row_shape(row, SESSION_COLUMNS)
        issues = []
        session_id = values["session_id"]
        try:
            validate_session_id(session_id)
        except InvalidRecordError as error:
            issues.extend(error.issues)

        participant = None
        try:
            validate_participant_id(values["participant_id"])
            participant = self._find_participant(values["participant_id"])
        except InvalidRecordError as error:     # also catches UnknownParticipantError
            issues.extend(error.issues)

        try:
            observation = Observation(
                timestamp=to_number(values["timestamp"], int),
                source_file=source_file,
                row_number=line_number,
                **{field: to_number(values[field]) for field in SESSION_COLUMNS[3:]},
            )
        except InvalidRecordError as error:
            issues.extend(error.issues)

        if issues:
            raise InvalidRecordError(issues)

        session = self.sessions.get(session_id)
        if session is None:
            session = TrainingSession(session_id, participant)
        elif session.participant is not participant:
            raise InvalidRecordError(("participant_id",
                                      f"session {session_id} already belongs to "
                                      f"{session.participant.participant_id}, not {participant.participant_id}"))
        session.add_observation(observation)
        self.sessions[session_id] = session

    def _find_participant(self, participant_id):
        try:
            return self.participants[participant_id]
        except KeyError:
            raise UnknownParticipantError(participant_id) from None
