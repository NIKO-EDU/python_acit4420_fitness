from data_generator import generate_fitness_data

# --- Generated scenarios ----------------------------------------------------
# (session id, participant id, participant name, age, generator scenario, seed)
GENERATED_SCENARIOS = [
    ("S01", "P001", "Ingrid", 29, "resting", 11),
    ("S02", "P002", "Omar", 41, "moderate_activity", 22),
    ("S03", "P003", "Sofie", 24, "high_activity", 33),
    ("S04", "P004", "Jonas", 35, "recovery", 44),
    ("S05", "P005", "Amina", 52, "poor_quality", 55),
]


def generated_scenarios():
    """Return a list of scenario dictionaries built from the generator."""
    scenarios = []
    for session_id, pid, name, age, scenario, seed in GENERATED_SCENARIOS:
        profile, observations = generate_fitness_data(
            participant_id=pid, scenario=scenario, seed=seed, number_of_windows=12)
        scenarios.append({
            "session_id": session_id,
            "title": scenario.replace("_", " "),
            "participant": {"name": name, "age": age, "profile": profile},
            "observations": observations,
        })
    return scenarios


# --- Hand-written unusual / invalid scenarios --------------------------------
def _window(t, hr, activity, quality=0.95, skin=2.0, temp=32.6):
    return {"timestamp": t, "heart_rate": hr, "skin_response": skin,
            "temperature": temp, "activity_level": activity, "signal_quality": quality}


CUSTOM_PROFILE = {
    "participant_id": "P006",
    "baseline_heart_rate": 64,
    "baseline_skin_response": 1.8,
    "baseline_temperature": 32.4,
}

# Heart rate raised but the participant barely moves (stress / heat / fever).
STRESS_WITHOUT_MOVEMENT = [
    _window(t, hr, 0.05, skin=3.4, temp=33.9)
    for t, hr in enumerate([98, 101, 104, 102, 106, 103, 105, 100])
]

# Mostly good moderate data mixed with problems that should be flagged or
# rejected individually without spoiling the whole session.
MIXED_QUALITY = [
    _window(0, 105, 0.50),
    _window(1, 108, 0.55, quality=0.65),             # flagged: mediocre signal
    _window(2, 110, 0.52, temp=None),                # flagged: temperature missing
    _window(2, 111, 0.52),                           # rejected: duplicate timestamp
    _window(3, "112", 0.50),                         # rejected: heart rate is text
    _window(4, 109, True),                           # rejected: activity is a boolean
    "corrupted packet",                              # rejected: not a dictionary
    _window(5, 190, 0.60),                           # flagged: above estimated max
    _window(6, 112, 0.58),
    _window(7, 107, 0.49),
]

# Clean data but far too short to judge.
TOO_SHORT = [_window(0, 70, 0.1), _window(1, 72, 0.1), _window(2, 71, 0.1)]


def custom_scenarios():
    """Return hand-written scenarios for unusual and invalid cases."""
    participant = {"name": "Lars", "age": 30, "profile": CUSTOM_PROFILE}
    return [
        {"session_id": "S06", "title": "raised heart rate without movement",
         "participant": participant, "observations": STRESS_WITHOUT_MOVEMENT},
        {"session_id": "S07", "title": "mixed quality with invalid records",
         "participant": participant, "observations": MIXED_QUALITY},
        {"session_id": "S08", "title": "too few windows",
         "participant": participant, "observations": TOO_SHORT},
    ]


def all_scenarios():
    return generated_scenarios() + custom_scenarios()
