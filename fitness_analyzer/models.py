"""Domain classes for the Smart Fitness Session Analyzer."""

import math

from .analysis import (
    classify_session,
    compare_with_reference,
    describe_physiology,
    detect_recovery,
    find_unusual_patterns,
    session_status,
    summarize,
)
from .exceptions import InvalidRecordError
from .validation import validate_participant_id, validate_session_id

MEASUREMENT_FIELDS = ("heart_rate", "skin_response", "temperature",
                      "activity_level", "signal_quality")


class RangeRule:
    """Checks that a value is there, is a number and is inside a plausible range.

    check() raises InvalidRecordError for values that are impossible, which
    means the whole CSV row gets rejected. assess() judges a value that passed
    check() and returns "ok", "flag" (usable, with a warning) or "exclude"
    (valid row but not used in the analysis).
    """

    def __init__(self, field, low, high, unit="", required=True):
        self.field = field
        self.low = low
        self.high = high
        self.unit = unit
        self.required = required

    def check(self, value):
        if value is None:
            if self.required:
                raise InvalidRecordError((self.field, "required value is missing"))
            return None
        # bool is a subclass of int, so it must be excluded explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise InvalidRecordError((self.field, f"{value!r} is not a number"))
        if not self.low <= value <= self.high:
            raise InvalidRecordError((self.field, f"{value}{self.unit} is outside the plausible "
                                                  f"range {self.low}-{self.high}{self.unit}"))
        return value

    def assess(self, value):
        if value is None:
            return "flag", f"{self.field} is missing"
        return "ok", ""

    def __repr__(self):
        return f"{type(self).__name__}({self.field!r}, {self.low}-{self.high})"


class SignalQualityRule(RangeRule):
    """Poor signal is a data-quality problem, not an invalid row.

    Below 0.5 the window is kept but excluded from the analysis, and below 0.7
    it is flagged.
    """

    def __init__(self, exclude_below=0.5, flag_below=0.7):
        super().__init__("signal_quality", 0.0, 1.0)
        self.exclude_below = exclude_below
        self.flag_below = flag_below

    def assess(self, value):
        status, message = super().assess(value)
        if status != "ok":
            return status, message
        if value < self.exclude_below:
            return "exclude", f"signal quality {value} is below {self.exclude_below}"
        if value < self.flag_below:
            return "flag", f"signal quality {value} is below {self.flag_below}"
        return "ok", ""


class ReferenceProfile:
    """A participant's personal reference (baseline) measurements."""

    DEFAULT_AGE = 35   # the CSV has no age column, so this is used for max HR
    RULES = (
        RangeRule("baseline_heart_rate", 30, 120, " bpm"),
        RangeRule("baseline_skin_response", 0, 30),
        RangeRule("baseline_temperature", 25, 40, " C"),
    )

    def __init__(self, resting_heart_rate, max_heart_rate,
                 baseline_skin_response, baseline_temperature):
        values = {
            "baseline_heart_rate": resting_heart_rate,
            "baseline_skin_response": baseline_skin_response,
            "baseline_temperature": baseline_temperature,
        }
        issues = []
        for rule in self.RULES:
            try:
                rule.check(values[rule.field])
            except InvalidRecordError as error:
                issues.extend(error.issues)
        if not issues:
            if baseline_skin_response <= 0:
                issues.append(("baseline_skin_response", "baseline skin response must be positive"))
            if max_heart_rate <= resting_heart_rate + 20:
                issues.append(("max_heart_rate", "maximum heart rate must be well above resting heart rate"))
        if issues:
            raise InvalidRecordError(issues)
        self.resting_heart_rate = resting_heart_rate
        self.max_heart_rate = max_heart_rate
        self.baseline_skin_response = baseline_skin_response
        self.baseline_temperature = baseline_temperature

    @staticmethod
    def estimate_max_heart_rate(age):
        """Estimate maximum heart rate with the Tanaka formula (208 - 0.7 x age)."""
        if not 10 <= age <= 100:
            raise ValueError(f"age {age} is outside the supported range 10-100")
        return round(208 - 0.7 * age, 1)

    @classmethod
    def from_profile(cls, profile, age=None):
        """Make a profile from a dict with baseline_* keys (a CSV row or the old generator)."""
        age = cls.DEFAULT_AGE if age is None else age
        return cls(
            resting_heart_rate=profile["baseline_heart_rate"],
            max_heart_rate=cls.estimate_max_heart_rate(age),
            baseline_skin_response=profile["baseline_skin_response"],
            baseline_temperature=profile["baseline_temperature"],
        )

    @property
    def heart_rate_reserve(self):
        return self.max_heart_rate - self.resting_heart_rate

    def to_dict(self):
        return {
            "resting_heart_rate": self.resting_heart_rate,
            "max_heart_rate": self.max_heart_rate,
            "baseline_skin_response": self.baseline_skin_response,
            "baseline_temperature": self.baseline_temperature,
        }

    def __repr__(self):
        return (f"ReferenceProfile(rest={self.resting_heart_rate}, max={self.max_heart_rate}, "
                f"skin={self.baseline_skin_response}, temp={self.baseline_temperature})")


class Participant:
    """A person wearing the device. Composes a ReferenceProfile."""

    def __init__(self, participant_id, reference, name=None, age=None):
        self._participant_id = validate_participant_id(participant_id)
        self.name = name or self._participant_id
        self.age = age
        self._reference = None
        self.reference = reference          # goes through the validating setter

    @property
    def participant_id(self):
        """Read-only: an identifier must not change once sessions refer to it."""
        return self._participant_id

    @property
    def reference(self):
        return self._reference

    @reference.setter
    def reference(self, value):
        if not isinstance(value, ReferenceProfile):
            raise TypeError("reference must be a ReferenceProfile")
        self._reference = value

    def to_dict(self):
        return {"participant_id": self.participant_id, "name": self.name, "age": self.age}

    def __repr__(self):
        return f"Participant({self.participant_id!r}, name={self.name!r})"


class Observation:
    """One window of data. Validates itself when it is created.

    Impossible values raise InvalidRecordError, so the observation is never
    created. Otherwise the status is "valid", "flagged" or "excluded".
    """

    RULES = (
        RangeRule("heart_rate", 30, 220, " bpm"),
        RangeRule("skin_response", 0, 30, required=False),
        RangeRule("temperature", 20, 42, " C", required=False),
        RangeRule("activity_level", 0.0, 1.0),
        SignalQualityRule(),
    )

    def __init__(self, timestamp, heart_rate=None, skin_response=None,
                 temperature=None, activity_level=None, signal_quality=None,
                 source_file=None, row_number=None):
        self.source_file = source_file      # where the row came from, for the reports
        self.row_number = row_number
        self._status = "valid"
        self._issues = []
        values = {
            "heart_rate": heart_rate,
            "skin_response": skin_response,
            "temperature": temperature,
            "activity_level": activity_level,
            "signal_quality": signal_quality,
        }
        self._validate(timestamp, values)
        self.timestamp = timestamp
        self._values = values

    @classmethod
    def from_dict(cls, data):
        """Create an observation from a raw dictionary."""
        if not isinstance(data, dict):
            raise InvalidRecordError((None, f"record is not a dictionary ({type(data).__name__})"))
        return cls(data.get("timestamp"), **{f: data.get(f) for f in MEASUREMENT_FIELDS})

    def _validate(self, timestamp, values):
        issues = []
        if timestamp is None:
            issues.append(("timestamp", "required value is missing"))
        elif isinstance(timestamp, bool) or not isinstance(timestamp, int):
            issues.append(("timestamp", f"{timestamp!r} is not a whole number"))
        elif timestamp < 0:
            issues.append(("timestamp", f"{timestamp} is negative"))
        for rule in self.RULES:
            try:
                rule.check(values[rule.field])
            except InvalidRecordError as error:
                issues.extend(error.issues)
        if issues:
            raise InvalidRecordError(issues)

        for rule in self.RULES:
            status, message = rule.assess(values[rule.field])
            if status == "exclude":
                self.exclude(message)
            elif status == "flag":
                self.flag(message)

    def exclude(self, message):
        self._status = "excluded"
        self._issues.append(message)

    def flag(self, message):
        if self._status == "valid":
            self._status = "flagged"
        self._issues.append(message)

    @property
    def source(self):
        if self.source_file is None:
            return None
        return f"{self.source_file} row {self.row_number}"

    @property
    def status(self):
        return self._status

    @property
    def is_usable(self):
        return self._status != "excluded"

    @property
    def issues(self):
        return list(self._issues)          # a copy, so callers cannot edit it

    def get(self, field):
        return self._values[field]

    def __repr__(self):
        return f"Observation(t={self.timestamp}, status={self.status}, hr={self.get('heart_rate')})"


class TrainingSession:
    """A participant's session: composes a Participant and a list of Observations."""

    def __init__(self, session_id, participant, observations=None):
        if not isinstance(participant, Participant):
            raise TypeError("participant must be a Participant")
        self.session_id = validate_session_id(session_id)
        self.participant = participant
        self._observations = []
        for item in observations or []:
            self.add_observation(item)

    def add_observation(self, item):
        """Add a raw dictionary or an Observation, applying session-level checks.

        Raises InvalidRecordError if the timestamp is duplicated or out of order.
        """
        obs = item if isinstance(item, Observation) else Observation.from_dict(item)
        if self._observations and obs.timestamp <= self._observations[-1].timestamp:
            last = self._observations[-1]
            where = f" ({last.source})" if last.source else ""
            raise InvalidRecordError(("timestamp", f"timestamp {obs.timestamp} is duplicated or out of "
                                                   f"order in {self.session_id}; previous was "
                                                   f"{last.timestamp}{where}"))
        if obs.is_usable and obs.get("heart_rate") > self.participant.reference.max_heart_rate:
            obs.flag("heart rate is above the participant's estimated maximum")
        self._observations.append(obs)
        return obs

    @property
    def observations(self):
        return tuple(self._observations)

    @property
    def usable_observations(self):
        return [o for o in self._observations if o.is_usable]

    @property
    def source_files(self):
        return sorted({o.source_file for o in self._observations if o.source_file})

    def count_by_status(self):
        counts = {"received": len(self._observations), "valid": 0, "flagged": 0, "excluded": 0}
        for obs in self._observations:
            counts[obs.status] += 1
        counts["usable"] = counts["valid"] + counts["flagged"]
        return counts

    def analyze(self):
        """Analyze the session and return a structured result dictionary."""
        usable = self.usable_observations
        reference = self.participant.reference
        counts = self.count_by_status()

        summaries = {
            field: summarize([o.get(field) for o in usable if o.get(field) is not None])
            for field in MEASUREMENT_FIELDS
        }
        comparison = compare_with_reference(summaries, reference.to_dict())
        recovery = detect_recovery(
            [o.get("heart_rate") for o in usable],
            [o.get("activity_level") for o in usable],
            reference.resting_heart_rate, reference.max_heart_rate,
        )
        mean_activity = summaries["activity_level"]["mean"] or 0.0
        label, explanation = classify_session(
            counts["usable"], counts["received"], comparison, mean_activity, recovery)
        unusual = []
        if label != "insufficient data":
            unusual = find_unusual_patterns(label, mean_activity, comparison)
            if label != "resting":
                explanation += describe_physiology(comparison)

        issues = [
            {"timestamp": o.timestamp, "source": o.source, "status": o.status, "message": message}
            for o in self._observations for message in o.issues
        ]
        return {
            "session_id": self.session_id,
            "participant": self.participant.to_dict(),
            "reference": reference.to_dict(),
            "source_files": self.source_files,
            "counts": counts,
            "summaries": summaries,
            "comparison": comparison,
            "recovery": recovery,
            "classification": label,
            "status": session_status(label, unusual),
            "explanation": explanation,
            "unusual": unusual,
            "issues": issues,
        }

    def __len__(self):
        return len(self._observations)

    def __repr__(self):
        return f"TrainingSession({self.session_id!r}, {self.participant.participant_id}, {len(self)} windows)"
