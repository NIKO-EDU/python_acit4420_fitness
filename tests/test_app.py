import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

import main
from fitness_analyzer.app import FitnessAnalyzerApp
from fitness_analyzer.exceptions import DataFileError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROFILES = DATA_DIR / "participants.csv"
SESSIONS = [DATA_DIR / "fitness_sessions.csv", DATA_DIR / "fitness_sessions_invalid.csv"]


class EndToEndTests(unittest.TestCase):
    EXPECTED = {
        "FIT-2026-001": ("resting", "normal"),
        "FIT-2026-002": ("moderate activity", "normal"),
        "FIT-2026-003": ("high activity", "normal"),
        "FIT-2026-004": ("recovering", "normal"),
        "FIT-2026-005": ("insufficient data", "insufficient data"),
        "FIT-2026-101": ("insufficient data", "insufficient data"),
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name) / "nested" / "output"   # does not exist yet

    def tearDown(self):
        self.tmp.cleanup()

    def test_official_data_produces_reports(self):
        summary = FitnessAnalyzerApp(PROFILES, SESSIONS, self.output).run()
        self.assertEqual(summary.accepted_rows, 30)
        self.assertEqual(summary.rejected_rows, 10)
        for name in ["analysis_summary.csv", "analysis_report.txt", "rejected_records.txt"]:
            self.assertTrue((self.output / name).is_file(), name)

        with open(self.output / "analysis_summary.csv", encoding="utf-8", newline="") as handle:
            rows = {row["session_id"]: row for row in csv.DictReader(handle)}
        self.assertEqual(list(rows), sorted(self.EXPECTED))
        for session_id, (label, status) in self.EXPECTED.items():
            self.assertEqual((rows[session_id]["classification"], rows[session_id]["status"]),
                             (label, status), session_id)

    def test_rejected_report_lists_rows_and_excluded_windows(self):
        FitnessAnalyzerApp(PROFILES, SESSIONS, self.output).run()
        text = (self.output / "rejected_records.txt").read_text(encoding="utf-8")
        self.assertIn("fitness_sessions_invalid.csv, row 8", text)
        self.assertIn("unknown participant 'P999'", text)
        self.assertIn("fitness_sessions.csv row 26 (FIT-2026-005", text)

    def test_second_run_gives_identical_output(self):
        FitnessAnalyzerApp(PROFILES, SESSIONS, self.output).run()
        first = {p.name: p.read_bytes() for p in self.output.iterdir()}
        FitnessAnalyzerApp(PROFILES, SESSIONS, self.output).run()
        second = {p.name: p.read_bytes() for p in self.output.iterdir()}
        self.assertEqual(first, second)

    def test_missing_session_file_is_skipped(self):
        paths = [SESSIONS[0], DATA_DIR / "no_such_file.csv"]
        summary = FitnessAnalyzerApp(PROFILES, paths, self.output).run()
        self.assertEqual(summary.accepted_rows, 29)
        self.assertEqual(len(summary.file_errors), 1)
        text = (self.output / "rejected_records.txt").read_text(encoding="utf-8")
        self.assertIn("no_such_file.csv: file not found", text)

    def test_missing_profile_file_is_fatal(self):
        with self.assertRaises(DataFileError):
            FitnessAnalyzerApp(DATA_DIR / "nope.csv", SESSIONS, self.output).run()

    def test_command_line(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main.main(["--profiles", str(PROFILES), "--sessions", *map(str, SESSIONS),
                              "--output", str(self.output)])
        self.assertEqual(code, 0)
        self.assertIn("Accepted rows    : 30", stdout.getvalue())
        self.assertIn("Rejected rows    : 10", stdout.getvalue())

    def test_command_line_missing_profiles_returns_error(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main.main(["--profiles", "missing.csv", "--output", str(self.output)])
        self.assertEqual(code, 1)
        self.assertIn("file not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
