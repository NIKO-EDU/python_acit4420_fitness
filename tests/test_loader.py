import tempfile
import unittest
from pathlib import Path

from fitness_analyzer.exceptions import DataFileError
from fitness_analyzer.loader import DataLoader

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SESSION_HEADER = ("session_id,participant_id,timestamp,heart_rate,skin_response,"
                  "temperature,activity_level,signal_quality")
PARTICIPANT_HEADER = "participant_id,name,baseline_heart_rate,baseline_skin_response,baseline_temperature"


def write_csv(directory, name, header, rows):
    path = Path(directory) / name
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


class OfficialDataTests(unittest.TestCase):
    def setUp(self):
        self.loader = DataLoader()
        self.loader.load_participants(DATA_DIR / "participants.csv")

    def test_participants_are_typed(self):
        participant = self.loader.participants["P003"]
        self.assertEqual(participant.name, "Maya Chen")
        self.assertEqual(participant.reference.resting_heart_rate, 63.0)

    def test_valid_file_is_fully_accepted_and_grouped(self):
        accepted = self.loader.load_sessions(DATA_DIR / "fitness_sessions.csv")
        self.assertEqual(accepted, 29)
        self.assertEqual(self.loader.rejected, [])
        self.assertEqual(sorted(self.loader.sessions),
                         ["FIT-2026-001", "FIT-2026-002", "FIT-2026-003", "FIT-2026-004", "FIT-2026-005"])
        session = self.loader.sessions["FIT-2026-004"]
        self.assertEqual(session.participant.participant_id, "P001")
        self.assertEqual(len(session), 6)

    def test_invalid_file_rows_are_rejected_with_context(self):
        accepted = self.loader.load_sessions(DATA_DIR / "fitness_sessions_invalid.csv")
        self.assertEqual(accepted, 1)
        self.assertEqual(len(self.loader.rejected), 10)
        by_row = {record.row_number: record for record in self.loader.rejected}
        self.assertEqual(by_row[3].issues[0][0], "heart_rate")
        self.assertEqual(by_row[4].issues[0][0], "participant_id")
        self.assertEqual(by_row[5].issues, [("activity_level", "required value is missing")])
        self.assertIn("unknown participant", by_row[8].issues[0][1])
        self.assertEqual(len(by_row[11].issues), 3)
        self.assertIsNone(by_row[12].issues[0][0])      # wrong number of fields
        self.assertTrue(all(r.source_file == "fitness_sessions_invalid.csv" for r in self.loader.rejected))


class FileErrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.loader = DataLoader()
        self.loader.load_participants(DATA_DIR / "participants.csv")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file(self):
        with self.assertRaises(DataFileError) as context:
            self.loader.load_sessions(self.dir / "does_not_exist.csv")
        self.assertIn("file not found", str(context.exception))

    def test_missing_profile_file(self):
        with self.assertRaises(DataFileError):
            DataLoader().load_participants(self.dir / "missing.csv")

    def test_directory_instead_of_file(self):
        folder = self.dir / "folder.csv"
        folder.mkdir()
        with self.assertRaises(DataFileError):
            self.loader.load_sessions(folder)

    def test_empty_file(self):
        path = self.dir / "empty.csv"
        path.write_text("", encoding="utf-8")
        with self.assertRaises(DataFileError):
            self.loader.load_sessions(path)

    def test_wrong_header(self):
        path = write_csv(self.dir, "s.csv", "id,participant,time", ["FIT-2026-001,P001,0"])
        with self.assertRaises(DataFileError) as context:
            self.loader.load_sessions(path)
        self.assertIn("unexpected header", str(context.exception))

    def test_invalid_utf8(self):
        path = self.dir / "bad.csv"
        path.write_bytes(SESSION_HEADER.encode() + b"\nFIT-2026-001,P\xff01,0,80,1,32,0.1,0.9\n")
        with self.assertRaises(DataFileError):
            self.loader.load_sessions(path)

    def test_profile_rows_are_validated(self):
        path = write_csv(self.dir, "p.csv", PARTICIPANT_HEADER, [
            "P001,Ok Person,68,1.2,32.4",
            "X1,Bad Id,68,1.2,32.4",
            "P002,,abc,1.2,32.4",
            "P001,Duplicate,68,1.2,32.4",
        ])
        loader = DataLoader()
        loader.load_participants(path)
        self.assertEqual(list(loader.participants), ["P001"])
        fields = [[field for field, _ in r.issues] for r in loader.rejected]
        self.assertEqual(fields, [["participant_id"], ["name", "baseline_heart_rate"], ["participant_id"]])

    def test_profile_file_with_no_valid_rows(self):
        path = write_csv(self.dir, "p.csv", PARTICIPANT_HEADER, ["X1,Bad,abc,1,32"])
        with self.assertRaises(DataFileError):
            DataLoader().load_participants(path)


class SessionConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.loader = DataLoader()
        self.loader.load_participants(DATA_DIR / "participants.csv")

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicate_timestamp_is_rejected(self):
        path = write_csv(self.dir, "s.csv", SESSION_HEADER, [
            "FIT-2026-001,P001,0,70,1.2,32.4,0.1,0.9",
            "FIT-2026-001,P001,0,71,1.2,32.4,0.1,0.9",
        ])
        self.assertEqual(self.loader.load_sessions(path), 1)
        self.assertIn("duplicated or out of order", self.loader.rejected[0].issues[0][1])

    def test_session_cannot_switch_participant(self):
        path = write_csv(self.dir, "s.csv", SESSION_HEADER, [
            "FIT-2026-001,P001,0,70,1.2,32.4,0.1,0.9",
            "FIT-2026-001,P002,1,71,1.2,32.4,0.1,0.9",
        ])
        self.loader.load_sessions(path)
        self.assertIn("already belongs to P001", self.loader.rejected[0].issues[0][1])

    def test_poor_signal_row_is_accepted_but_excluded(self):
        path = write_csv(self.dir, "s.csv", SESSION_HEADER, ["FIT-2026-001,P001,0,70,1.2,32.4,0.1,0.2"])
        self.assertEqual(self.loader.load_sessions(path), 1)
        self.assertEqual(self.loader.sessions["FIT-2026-001"].observations[0].status, "excluded")

    def test_blank_lines_are_ignored(self):
        path = write_csv(self.dir, "s.csv", SESSION_HEADER, ["", "FIT-2026-001,P001,0,70,1.2,32.4,0.1,0.9", ""])
        self.assertEqual(self.loader.load_sessions(path), 1)
        self.assertEqual(self.loader.rejected, [])


if __name__ == "__main__":
    unittest.main()
