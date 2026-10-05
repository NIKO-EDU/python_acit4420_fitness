import unittest

from fitness_analyzer.analysis import format_report
from fitness_analyzer.exceptions import InvalidIdentifierError, InvalidRecordError
from fitness_analyzer.models import (
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


class RuleTests(unittest.TestCase):
    def test_range_rule(self):
        rule = RangeRule("heart_rate", 30, 220)
        self.assertEqual(rule.check(80), 80)
        for bad in (None, 300, "80", True, float("nan"), float("inf")):
            with self.subTest(value=bad), self.assertRaises(InvalidRecordError):
                rule.check(bad)

    def test_range_rule_boundaries_are_inclusive(self):
        rule = RangeRule("activity_level", 0.0, 1.0)
        self.assertEqual(rule.check(0.0), 0.0)
        self.assertEqual(rule.check(1.0), 1.0)
        with self.assertRaises(InvalidRecordError):
            rule.check(1.01)

    def test_error_names_the_field(self):
        with self.assertRaises(InvalidRecordError) as context:
            RangeRule("heart_rate", 30, 220).check(-15)
        self.assertEqual(context.exception.issues[0][0], "heart_rate")

    def test_optional_field_is_flagged_not_rejected(self):
        rule = RangeRule("temperature", 20, 42, required=False)
        self.assertIsNone(rule.check(None))
        self.assertEqual(rule.assess(None)[0], "flag")

    def test_signal_quality_rule_overrides_assess(self):
        rule = SignalQualityRule()
        self.assertEqual(rule.assess(0.95)[0], "ok")
        self.assertEqual(rule.assess(0.7)[0], "ok")
        self.assertEqual(rule.assess(0.6)[0], "flag")
        self.assertEqual(rule.assess(0.5)[0], "flag")
        self.assertEqual(rule.assess(0.49)[0], "exclude")
        with self.assertRaises(InvalidRecordError):
            rule.check(1.5)                              # inherited range check


class ObservationTests(unittest.TestCase):
    def test_observation_statuses(self):
        self.assertEqual(Observation.from_dict(window(0)).status, "valid")
        self.assertEqual(Observation.from_dict(window(0, quality=0.6)).status, "flagged")
        self.assertEqual(Observation.from_dict(window(0, temperature=None)).status, "flagged")
        self.assertEqual(Observation.from_dict(window(0, quality=0.3)).status, "excluded")

    def test_invalid_observations_raise(self):
        for data in (window(0, hr=None), window(-1), window("two"), window(1.5), "garbage"):
            with self.subTest(data=data), self.assertRaises(InvalidRecordError):
                Observation.from_dict(data)

    def test_all_problems_are_reported_together(self):
        with self.assertRaises(InvalidRecordError) as context:
            Observation.from_dict(window(0, skin_response=-0.5, temperature=55.0, activity=1.3))
        fields = [field for field, _ in context.exception.issues]
        self.assertEqual(fields, ["skin_response", "temperature", "activity_level"])

    def test_issues_are_a_copy(self):
        obs = Observation.from_dict(window(0, quality=0.6))
        obs.issues.clear()
        self.assertTrue(obs.issues)

    def test_source(self):
        obs = Observation(0, 80, 2.0, 32.5, 0.2, 0.9, source_file="a.csv", row_number=5)
        self.assertEqual(obs.source, "a.csv row 5")


class ClassTests(unittest.TestCase):
    def test_estimate_max_heart_rate(self):
        self.assertEqual(ReferenceProfile.estimate_max_heart_rate(40), 180.0)
        with self.assertRaises(ValueError):
            ReferenceProfile.estimate_max_heart_rate(5)

    def test_from_profile_uses_default_age(self):
        ref = ReferenceProfile.from_profile({"baseline_heart_rate": 68, "baseline_skin_response": 1.2,
                                             "baseline_temperature": 32.4})
        self.assertEqual(ref.resting_heart_rate, 68)
        self.assertEqual(ref.max_heart_rate, 183.5)

    def test_invalid_reference_rejected(self):
        with self.assertRaises(InvalidRecordError):
            ReferenceProfile(200, 180, 2.0, 32.5)
        with self.assertRaises(InvalidRecordError):
            ReferenceProfile("abc", 180, 2.0, 32.5)
        with self.assertRaises(InvalidRecordError):
            ReferenceProfile(60, 180, 0, 32.5)

    def test_participant_id_is_validated(self):
        reference = make_participant().reference
        with self.assertRaises(InvalidIdentifierError):
            Participant("001", reference)

    def test_participant_encapsulation(self):
        participant = make_participant()
        with self.assertRaises(AttributeError):
            participant.participant_id = "other"
        with self.assertRaises(TypeError):
            participant.reference = {"resting_heart_rate": 60}

    def test_session_id_is_validated(self):
        with self.assertRaises(InvalidIdentifierError):
            TrainingSession("FIT-26-102", make_participant())

    def test_session_rejects_duplicate_timestamp(self):
        session = TrainingSession("FIT-2026-001", make_participant(), [window(0), window(1)])
        with self.assertRaises(InvalidRecordError):
            session.add_observation(window(1))
        self.assertEqual(session.count_by_status()["usable"], 2)

    def test_session_rejects_out_of_order_timestamp(self):
        session = TrainingSession("FIT-2026-001", make_participant(), [window(0), window(2)])
        with self.assertRaises(InvalidRecordError):
            session.add_observation(window(1))

    def test_session_flags_heart_rate_above_maximum(self):
        session = TrainingSession("FIT-2026-001", make_participant(age=60), [window(0, hr=200)])
        self.assertEqual(session.observations[0].status, "flagged")

    def test_analyze_returns_structured_dictionary(self):
        session = TrainingSession("FIT-2026-001", make_participant(), [window(t) for t in range(6)])
        result = session.analyze()
        for key in ("session_id", "participant", "counts", "summaries", "comparison", "recovery",
                    "classification", "status", "explanation", "unusual", "issues", "source_files"):
            self.assertIn(key, result)
        self.assertIsInstance(format_report(result), str)

    def test_raised_heart_rate_without_movement_is_unusual(self):
        windows = [window(t, hr=hr, activity=0.05)
                   for t, hr in enumerate([98, 101, 104, 102, 106, 103, 105, 100])]
        result = TrainingSession("FIT-2026-006", make_participant(resting=64), windows).analyze()
        self.assertEqual(result["classification"], "moderate activity")
        self.assertEqual(result["status"], "unusual")

    def test_poor_signal_session_is_insufficient(self):
        windows = [window(t, quality=0.3) for t in range(6)]
        result = TrainingSession("FIT-2026-005", make_participant(), windows).analyze()
        self.assertEqual(result["status"], "insufficient data")
        self.assertEqual(result["counts"]["excluded"], 6)


if __name__ == "__main__":
    unittest.main()
