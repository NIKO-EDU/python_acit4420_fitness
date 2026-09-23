"""Domain classes for the Smart Fitness Session Analyzer."""

import math

from analysis import (
    classify_session,
    compare_with_reference,
    describe_physiology,
    detect_recovery,
    summarize,
)

MEASUREMENT_FIELDS = ("heart_rate", "skin_response", "temperature",
                      "activity_level", "signal_quality")


class ReferenceProfile:
    """A participant's personal reference (baseline) measurements."""

    DEFAULT_AGE = 35   # used when the data source gives no age

    def __init__(self, resting_heart_rate, max_heart_rate,
                 baseline_skin_response, baseline_temperature):
        if not 30 <= resting_heart_rate <= 120:
            raise ValueError(f"resting heart rate {resting_heart_rate} is implausible")
        if max_heart_rate <= resting_heart_rate + 20:
            raise ValueError("maximum heart rate must be well above resting heart rate")
        if baseline_skin_response <= 0:
            raise ValueError("baseline skin response must be positive")
        if not 25 <= baseline_temperature <= 40:
            raise ValueError(f"baseline temperature {baseline_temperature} is implausible")
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
    def from_generator_profile(cls, profile, age=None):
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
    """A person wearing the device. Composes a :class:`ReferenceProfile`."""

    def __init__(self, participant_id, reference, name=None, age=None):
        if not isinstance(participant_id, str) or not participant_id.strip():
            raise ValueError("participant_id must be a non-empty string")
        self._participant_id = participant_id.strip()
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


class RangeRule:
    def __init__(self, field, low, high, unit="", required=True):
        self.field = field
        self.low = low
        self.high = high
        self.unit = unit
        self.required = required

    def check(self, value):
        if value is None:
            if self.required:
                return "reject", f"{self.field} is missing"
            return "flag", f"{self.field} is missing"
        # bool is a subclass of int, so it must be excluded explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
            return "reject", f"{self.field} is not a number ({value!r})"
        if not self.low <= value <= self.high:
            return "reject", (f"{self.field}={value}{self.unit} is outside the plausible "
                              f"range {self.low}-{self.high}{self.unit}")
        return "ok", ""

    def __repr__(self):
        return f"{type(self).__name__}({self.field!r}, {self.low}-{self.high})"


class SignalQualityRule(RangeRule):
    def __init__(self, reject_below=0.5, flag_below=0.7):
        super().__init__("signal_quality", 0.0, 1.0)
        self.reject_below = reject_below
        self.flag_below = flag_below

    def check(self, value):
        status, message = super().check(value)
        if status != "ok":
            return status, message
        if value < self.reject_below:
            return "reject", f"signal quality {value} is below {self.reject_below}"
        if value < self.flag_below:
            return "flag", f"signal quality {value} is below {self.flag_below}"
        return "ok", ""


class Observation:
    RULES = (
        RangeRule("heart_rate", 30, 220, " bpm"),
        RangeRule("skin_response", 0, 30, required=False),
        RangeRule("temperature", 20, 42, " C", required=False),
        RangeRule("activity_level", 0.0, 1.0),
        SignalQualityRule(),
    )

    def __init__(self, timestamp, heart_rate=None, skin_response=None,
                 temperature=None, activity_level=None, signal_quality=None):
        self.timestamp = timestamp
        self._values = {
            "heart_rate": heart_rate,
            "skin_response": skin_response,
            "temperature": temperature,
            "activity_level": activity_level,
            "signal_quality": signal_quality,
        }
        self._status = "valid"
        self._issues = []
        self._validate()

    @classmethod
    def from_dict(cls, data):
        """Create an observation from a raw dictionary such as the generator's."""
        if not isinstance(data, dict):
            obs = cls(timestamp=None)
            obs._issues.clear()
            obs.reject(f"record is not a dictionary ({type(data).__name__})")
            return obs
        return cls(data.get("timestamp"), **{f: data.get(f) for f in MEASUREMENT_FIELDS})

    def _validate(self):
        ts = self.timestamp
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts < 0:
            self.reject(f"timestamp {ts!r} is missing or invalid")
        for rule in self.RULES:
            status, message = rule.check(self._values[rule.field])
            if status == "reject":
                self.reject(message)
            elif status == "flag":
                self.flag(message)

    def reject(self, message):
        self._status = "rejected"
        self._issues.append(message)

    def flag(self, message):
        if self._status == "valid":
            self._status = "flagged"
        self._issues.append(message)

    @property
    def status(self):
        return self._status

    @property
    def is_usable(self):
        return self._status != "rejected"

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
        self.session_id = session_id
        self.participant = participant
        self._observations = []
        for item in observations or []:
            self.add_observation(item)

    def add_observation(self, item):
        """Add a raw dictionary or an Observation, applying session-level checks."""
        obs = item if isinstance(item, Observation) else Observation.from_dict(item)
        if obs.is_usable:
            previous = [o.timestamp for o in self._observations if o.is_usable]
            if previous and obs.timestamp <= previous[-1]:
                obs.reject(f"timestamp {obs.timestamp} is duplicated or out of order")
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

    def count_by_status(self):
        counts = {"received": len(self._observations), "valid": 0, "flagged": 0, "rejected": 0}
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
        if label != "insufficient data":
            explanation += describe_physiology(comparison)

        issues = [
            {"timestamp": o.timestamp, "status": o.status, "message": message}
            for o in self._observations for message in o.issues
        ]
        return {
            "session_id": self.session_id,
            "participant": self.participant.to_dict(),
            "reference": reference.to_dict(),
            "counts": counts,
            "summaries": summaries,
            "comparison": comparison,
            "recovery": recovery,
            "classification": label,
            "explanation": explanation,
            "issues": issues,
        }

    def __len__(self):
        return len(self._observations)

    def __repr__(self):
        return f"TrainingSession({self.session_id!r}, {self.participant.participant_id}, {len(self)} windows)"
