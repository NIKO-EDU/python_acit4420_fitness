import unittest

from analysis import (
    classify_session,
    detect_recovery,
    format_report,
    format_value,
    heart_rate_reserve_percent,
    summarize,
)
from data_generator import generate_fitness_data
from main import build_session, run_all
from models import (
    Observation,
    Participant,
    RangeRule,
    ReferenceProfile,
    SignalQualityRule,
    TrainingSession,
)


def make_participant(resting=60, age=30):
    reference = ReferenceProfile(resting, ReferenceProfile.estimate_max_heart_rate(age), 2.0, 32.5)
    return Participant("P100", reference, name="Test", age=age)


def window(t, hr=80, activity=0.2, quality=0.95, **extra):
    data = {"timestamp": t, "heart_rate": hr, "skin_response": 2.0, "temperature": 32.5,
            "activity_level": activity, "signal_quality": quality}
    data.update(extra)
    return data


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
        self.assertFalse(detect_recovery(hr, act, 60, 187)["detected"])

    def test_recovery_needs_enough_windows(self):
        self.assertFalse(detect_recovery([150, 90], [0.9, 0.1], 60, 187)["detected"])

    def test_classify_insufficient(self):
        label, reasons = classify_session(2, 10, {}, 0.0, {"detected": False})
        self.assertEqual(label, "insufficient data")
        self.assertIn("2 of 10", reasons[0])

    def test_classify_thresholds(self):
        no_recovery = {"detected": False}
        cases = [(5.0, "resting"), (30.0, "moderate activity"), (70.0, "high activity")]
        for hrr, expected in cases:
            label, _ = classify_session(10, 10, {"median_hrr_pct": hrr}, 0.5, no_recovery)
            self.assertEqual(label, expected)

    def test_format_value(self):
        self.assertEqual(format_value(None), "-")
        self.assertEqual(format_value(1.234, "%"), "1.2%")


class ValidationTests(unittest.TestCase):
    def test_range_rule(self):
        rule = RangeRule("heart_rate", 30, 220)
        self.assertEqual(rule.check(80)[0], "ok")
        self.assertEqual(rule.check(None)[0], "reject")
        self.assertEqual(rule.check(300)[0], "reject")
        self.assertEqual(rule.check("80")[0], "reject")
        self.assertEqual(rule.check(True)[0], "reject")
        self.assertEqual(rule.check(float("nan"))[0], "reject")

    def test_optional_field_is_flagged_not_rejected(self):
        self.assertEqual(RangeRule("temperature", 20, 42, required=False).check(None)[0], "flag")

    def test_signal_quality_rule_overrides_check(self):
        rule = SignalQualityRule()
        self.assertEqual(rule.check(0.95)[0], "ok")
        self.assertEqual(rule.check(0.6)[0], "flag")
        self.assertEqual(rule.check(0.3)[0], "reject")
        self.assertEqual(rule.check(1.5)[0], "reject")      # inherited range check

    def test_observation_statuses(self):
        self.assertEqual(Observation.from_dict(window(0)).status, "valid")
        self.assertEqual(Observation.from_dict(window(0, quality=0.6)).status, "flagged")
        self.assertEqual(Observation.from_dict(window(0, hr=None)).status, "rejected")
        self.assertEqual(Observation.from_dict(window(-1)).status, "rejected")
        self.assertEqual(Observation.from_dict("garbage").status, "rejected")

    def test_issues_are_a_copy(self):
        obs = Observation.from_dict(window(0, hr=None))
        obs.issues.clear()
        self.assertTrue(obs.issues)


class ClassTests(unittest.TestCase):
    def test_estimate_max_heart_rate(self):
        self.assertEqual(ReferenceProfile.estimate_max_heart_rate(40), 180.0)
        with self.assertRaises(ValueError):
            ReferenceProfile.estimate_max_heart_rate(5)

    def test_from_generator_profile(self):
        profile, _ = generate_fitness_data("P9", "resting", seed=1)
        ref = ReferenceProfile.from_generator_profile(profile, age=40)
        self.assertEqual(ref.resting_heart_rate, profile["baseline_heart_rate"])
        self.assertEqual(ref.max_heart_rate, 180.0)

    def test_invalid_reference_rejected(self):
        with self.assertRaises(ValueError):
            ReferenceProfile(200, 180, 2.0, 32.5)

    def test_participant_encapsulation(self):
        participant = make_participant()
        with self.assertRaises(AttributeError):
            participant.participant_id = "other"
        with self.assertRaises(TypeError):
            participant.reference = {"resting_heart_rate": 60}

    def test_session_rejects_duplicate_timestamp(self):
        session = TrainingSession("T", make_participant(), [window(0), window(1), window(1)])
        self.assertEqual(session.observations[2].status, "rejected")
        self.assertEqual(session.count_by_status()["usable"], 2)

    def test_session_flags_heart_rate_above_maximum(self):
        session = TrainingSession("T", make_participant(age=60), [window(0, hr=200)])
        self.assertEqual(session.observations[0].status, "flagged")

    def test_analyze_returns_structured_dictionary(self):
        session = TrainingSession("T", make_participant(), [window(t) for t in range(6)])
        result = session.analyze()
        for key in ("session_id", "participant", "counts", "summaries", "comparison",
                    "recovery", "classification", "explanation", "issues"):
            self.assertIn(key, result)
        self.assertIsInstance(format_report(result), str)


class ScenarioTests(unittest.TestCase):
    EXPECTED = {
        "S01": "resting",
        "S02": "moderate activity",
        "S03": "high activity",
        "S04": "recovering",
        "S05": "insufficient data",
        "S06": "moderate activity",
        "S07": "moderate activity",
        "S08": "insufficient data",
    }

    def test_all_scenarios(self):
        results = {r["session_id"]: r for _, r in run_all()}
        for session_id, expected in self.EXPECTED.items():
            self.assertEqual(results[session_id]["classification"], expected, session_id)

    def test_stress_scenario_explains_mismatch(self):
        results = {r["session_id"]: r for _, r in run_all()}
        self.assertTrue(any("movement is low" in r for r in results["S06"]["explanation"]))

    def test_generated_scenarios_across_seeds(self):
        expected = {"resting": "resting", "moderate_activity": "moderate activity",
                    "high_activity": "high activity", "recovery": "recovering",
                    "poor_quality": "insufficient data"}
        for scenario, label in expected.items():
            correct = 0
            for seed in range(50):
                profile, observations = generate_fitness_data("P1", scenario, seed, 12)
                session = build_session({"session_id": "x", "observations": observations,
                                         "participant": {"name": "x", "age": 35, "profile": profile}})
                correct += session.analyze()["classification"] == label
            self.assertGreaterEqual(correct, 48, scenario)


if __name__ == "__main__":
    unittest.main(verbosity=2)
