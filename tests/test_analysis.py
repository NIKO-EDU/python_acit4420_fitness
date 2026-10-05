import unittest

from data_generator import generate_fitness_data
from fitness_analyzer.analysis import (
    STATUS_INSUFFICIENT,
    STATUS_NORMAL,
    STATUS_UNUSUAL,
    classify_session,
    detect_recovery,
    find_unusual_patterns,
    format_value,
    heart_rate_reserve_percent,
    session_status,
    summarize,
)
from fitness_analyzer.exceptions import InvalidRecordError
from fitness_analyzer.models import Participant, ReferenceProfile, TrainingSession

NO_CHANGE = {"skin_response_change_pct": 0.0, "temperature_change": 0.0}


class FunctionTests(unittest.TestCase):
    def test_summarize(self):
        self.assertEqual(summarize([1, 2, 3, 10]),
                         {"count": 4, "mean": 4.0, "median": 2.5, "min": 1, "max": 10})

    def test_summarize_empty(self):
        self.assertEqual(summarize([])["count"], 0)
        self.assertIsNone(summarize([])["mean"])

    def test_heart_rate_reserve(self):
        self.assertEqual(heart_rate_reserve_percent(60, 60, 180), 0.0)
        self.assertEqual(heart_rate_reserve_percent(120, 60, 180), 50.0)
        self.assertEqual(heart_rate_reserve_percent(180, 60, 180), 100.0)
        with self.assertRaises(ValueError):
            heart_rate_reserve_percent(100, 80, 80)

    def test_recovery_detected(self):
        hr = [150, 155, 160, 158, 157, 156, 120, 100, 90]
        act = [0.8, 0.85, 0.9, 0.9, 0.85, 0.8, 0.3, 0.1, 0.05]
        result = detect_recovery(hr, act, 60, 187)
        self.assertTrue(result["detected"], result["reason"])

    def test_recovery_not_detected_when_heart_rate_rises_again(self):
        hr = [150, 155, 160, 158, 157, 156, 100, 95, 130]
        act = [0.8, 0.85, 0.9, 0.9, 0.85, 0.8, 0.1, 0.1, 0.1]
        result = detect_recovery(hr, act, 60, 187)
        self.assertFalse(result["detected"])
        self.assertIn("not falling at the end", result["reason"])

    def test_recovery_needs_enough_windows(self):
        self.assertFalse(detect_recovery([150, 90], [0.9, 0.1], 60, 187)["detected"])

    def test_recovery_with_exactly_six_windows(self):
        hr = [72, 138, 151, 132, 104, 82]          # FIT-2026-004 from the official data
        act = [0.20, 0.86, 0.92, 0.70, 0.42, 0.18]
        self.assertTrue(detect_recovery(hr, act, 68, 183.5)["detected"])

    def test_classify_insufficient(self):
        label, reasons = classify_session(2, 10, {}, 0.0, {"detected": False})
        self.assertEqual(label, "insufficient data")
        self.assertIn("2 of 10", reasons[0])

    def test_classify_usable_boundaries(self):
        no_recovery = {"detected": False}
        comparison = {"median_hrr_pct": 5.0}
        self.assertEqual(classify_session(4, 8, comparison, 0.1, no_recovery)[0], "resting")
        self.assertEqual(classify_session(3, 3, comparison, 0.1, no_recovery)[0], "insufficient data")
        self.assertEqual(classify_session(4, 9, comparison, 0.1, no_recovery)[0], "insufficient data")

    def test_classify_thresholds(self):
        no_recovery = {"detected": False}
        cases = [(5.0, "resting"), (15.0, "moderate activity"), (30.0, "moderate activity"),
                 (40.0, "high activity"), (70.0, "high activity")]
        for hrr, expected in cases:
            with self.subTest(hrr=hrr):
                label, _ = classify_session(10, 10, {"median_hrr_pct": hrr}, 0.5, no_recovery)
                self.assertEqual(label, expected)

    def test_unusual_raised_heart_rate_without_movement(self):
        findings = find_unusual_patterns("moderate activity", 0.05, NO_CHANGE)
        self.assertTrue(any("movement is low" in f for f in findings))

    def test_unusual_skin_and_temperature_only_count_at_rest(self):
        raised = {"skin_response_change_pct": 80.0, "temperature_change": 1.5}
        self.assertEqual(len(find_unusual_patterns("resting", 0.1, raised)), 2)
        self.assertEqual(find_unusual_patterns("high activity", 0.8, raised), [])

    def test_session_status(self):
        self.assertEqual(session_status("insufficient data", []), STATUS_INSUFFICIENT)
        self.assertEqual(session_status("resting", []), STATUS_NORMAL)
        self.assertEqual(session_status("resting", ["something odd"]), STATUS_UNUSUAL)

    def test_format_value(self):
        self.assertEqual(format_value(None), "-")
        self.assertEqual(format_value(1.234, "%"), "1.2%")


class GeneratorTests(unittest.TestCase):
    """The classification thresholds from Assignment I still hold on the generator's data."""

    EXPECTED = {"resting": "resting", "moderate_activity": "moderate activity",
                "high_activity": "high activity", "recovery": "recovering",
                "poor_quality": "insufficient data"}

    @staticmethod
    def build_session(profile, observations):
        participant = Participant("P001", ReferenceProfile.from_profile(profile))
        session = TrainingSession("FIT-2026-001", participant)
        for data in observations:
            try:
                session.add_observation(data)
            except InvalidRecordError:
                continue        # same as a rejected CSV row
        return session

    def test_generated_scenarios_across_seeds(self):
        for scenario, label in self.EXPECTED.items():
            correct = 0
            for seed in range(50):
                profile, observations = generate_fitness_data("P001", scenario, seed, 12)
                correct += self.build_session(profile, observations).analyze()["classification"] == label
            self.assertGreaterEqual(correct, 48, scenario)


if __name__ == "__main__":
    unittest.main()
