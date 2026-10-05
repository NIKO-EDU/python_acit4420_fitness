"""Calculations, classification and the text report for one session."""

import statistics

# --- Classification thresholds (explained in README.md) --------------------
MIN_USABLE_WINDOWS = 4          # fewer usable windows -> insufficient data
MIN_USABLE_FRACTION = 0.5       # more than half of the windows must be usable
RESTING_MAX_HRR = 15.0          # median % heart-rate reserve below this = resting
MODERATE_MAX_HRR = 40.0         # below this = moderate, at or above = high
RECOVERY_MIN_WINDOWS = 6        # need enough windows to split active / tail
RECOVERY_MIN_PEAK_HRR = 40.0    # must have reached high effort first
RECOVERY_MIN_HR_DROP = 15.0     # bpm drop from active part to final third
RECOVERY_MIN_ACTIVITY_DROP = 0.2
LOW_ACTIVITY = 0.3
HIGH_ACTIVITY = 0.5
SKIN_RESPONSE_NOTABLE_CHANGE = 50.0   # percent above personal baseline
TEMPERATURE_NOTABLE_CHANGE = 1.0      # degrees C away from personal baseline

STATUS_NORMAL = "normal"
STATUS_UNUSUAL = "unusual"
STATUS_INSUFFICIENT = "insufficient data"


def summarize(values):
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": round(float(statistics.mean(values)), 2),
        "median": float(statistics.median(values)),
        "min": min(values),
        "max": max(values),
    }


def heart_rate_reserve_percent(heart_rate, resting_heart_rate, max_heart_rate):
    reserve = max_heart_rate - resting_heart_rate
    if reserve <= 0:
        raise ValueError("maximum heart rate must be above resting heart rate")
    return round((heart_rate - resting_heart_rate) / reserve * 100, 1)


def compare_with_reference(summaries, reference):
    rest = reference["resting_heart_rate"]
    peak = reference["max_heart_rate"]
    hr = summaries["heart_rate"]
    comparison = {
        "mean_hr_above_resting": None,
        "mean_hrr_pct": None,
        "median_hrr_pct": None,
        "peak_hrr_pct": None,
        "skin_response_change_pct": None,
        "temperature_change": None,
    }
    if hr["count"]:
        comparison["mean_hr_above_resting"] = round(hr["mean"] - rest, 1)
        comparison["mean_hrr_pct"] = heart_rate_reserve_percent(hr["mean"], rest, peak)
        comparison["median_hrr_pct"] = heart_rate_reserve_percent(hr["median"], rest, peak)
        comparison["peak_hrr_pct"] = heart_rate_reserve_percent(hr["max"], rest, peak)

    skin = summaries["skin_response"]
    if skin["count"]:
        baseline = reference["baseline_skin_response"]
        comparison["skin_response_change_pct"] = round((skin["mean"] - baseline) / baseline * 100, 1)

    temp = summaries["temperature"]
    if temp["count"]:
        comparison["temperature_change"] = round(temp["mean"] - reference["baseline_temperature"], 2)
    return comparison


def detect_recovery(heart_rates, activity_levels, resting_heart_rate, max_heart_rate):
    result = {"detected": False, "reason": "", "hr_drop": None,
              "activity_drop": None, "peak_hrr_pct": None}
    n = len(heart_rates)
    if n < RECOVERY_MIN_WINDOWS or len(activity_levels) != n:
        result["reason"] = (f"only {n} usable windows; at least "
                            f"{RECOVERY_MIN_WINDOWS} are needed to assess recovery")
        return result

    tail_size = max(2, n // 3)
    active_hr, tail_hr = heart_rates[:-tail_size], heart_rates[-tail_size:]
    active_act, tail_act = activity_levels[:-tail_size], activity_levels[-tail_size:]

    hr_drop = round(statistics.mean(active_hr) - statistics.mean(tail_hr), 1)
    activity_drop = round(statistics.mean(active_act) - statistics.mean(tail_act), 2)
    peak_hrr = heart_rate_reserve_percent(max(active_hr), resting_heart_rate, max_heart_rate)
    still_falling = tail_hr[-1] < tail_hr[0]

    result.update(hr_drop=hr_drop, activity_drop=activity_drop, peak_hrr_pct=peak_hrr)
    checks = [
        (peak_hrr >= RECOVERY_MIN_PEAK_HRR,
         f"peak effort {peak_hrr}% HRR (need >= {RECOVERY_MIN_PEAK_HRR}%)"),
        (hr_drop >= RECOVERY_MIN_HR_DROP,
         f"heart rate fell {hr_drop} bpm in final {tail_size} windows (need >= {RECOVERY_MIN_HR_DROP})"),
        (activity_drop >= RECOVERY_MIN_ACTIVITY_DROP,
         f"activity fell {activity_drop} (need >= {RECOVERY_MIN_ACTIVITY_DROP})"),
        (still_falling, "heart rate still falling across the final windows" if still_falling
         else "heart rate is not falling at the end of the session"),
    ]
    result["detected"] = all(passed for passed, _ in checks)
    failed = [text for passed, text in checks if not passed]
    if result["detected"]:
        result["reason"] = "; ".join(text for _, text in checks)
    else:
        result["reason"] = "not detected: " + "; ".join(failed)
    return result


def classify_session(usable_count, received_count, comparison, mean_activity, recovery):
    reasons = []
    fraction = usable_count / received_count if received_count else 0.0
    if usable_count < MIN_USABLE_WINDOWS or fraction < MIN_USABLE_FRACTION:
        reasons.append(
            f"only {usable_count} of {received_count} windows were usable "
            f"({fraction:.0%}); need at least {MIN_USABLE_WINDOWS} and "
            f"{MIN_USABLE_FRACTION:.0%} of the session")
        return "insufficient data", reasons

    if recovery["detected"]:
        reasons.append("recovery pattern found: " + recovery["reason"])
        return "recovering", reasons

    # The median is used so that one flagged spike cannot change the label.
    hrr = comparison["median_hrr_pct"]
    if hrr < RESTING_MAX_HRR:
        label = "resting"
        reasons.append(f"median heart rate is {hrr}% of heart-rate reserve (< {RESTING_MAX_HRR}%)")
    elif hrr < MODERATE_MAX_HRR:
        label = "moderate activity"
        reasons.append(f"median heart rate is {hrr}% of heart-rate reserve "
                       f"({RESTING_MAX_HRR}-{MODERATE_MAX_HRR}%)")
    else:
        label = "high activity"
        reasons.append(f"median heart rate is {hrr}% of heart-rate reserve (>= {MODERATE_MAX_HRR}%)")

    reasons.append(f"mean activity level is {mean_activity:.2f}")
    return label, reasons


def find_unusual_patterns(label, mean_activity, comparison):
    """Return the things that don't fit the label (an empty list means a normal session).

    Raised skin response and temperature are expected during exercise, so
    they only count as unusual in a resting session.
    """
    findings = []
    if label in ("moderate activity", "high activity") and mean_activity < LOW_ACTIVITY:
        findings.append("heart rate is raised while movement is low - possible stress, "
                        "heat, illness or a sensor fault")
    elif label == "resting" and mean_activity >= HIGH_ACTIVITY:
        findings.append("movement is high but heart rate stays low - check the heart-rate sensor")
    if label == "resting":
        skin = comparison["skin_response_change_pct"]
        if skin is not None and skin >= SKIN_RESPONSE_NOTABLE_CHANGE:
            findings.append(f"skin response is {skin}% above baseline without exercise")
        temp = comparison["temperature_change"]
        if temp is not None and abs(temp) >= TEMPERATURE_NOTABLE_CHANGE:
            direction = "above" if temp > 0 else "below"
            findings.append(f"skin temperature is {abs(temp)} C {direction} baseline without exercise")
    return findings


def session_status(label, unusual):
    """Overall result: insufficient data, unusual or normal."""
    if label == "insufficient data":
        return STATUS_INSUFFICIENT
    return STATUS_UNUSUAL if unusual else STATUS_NORMAL


def describe_physiology(comparison):
    """Return extra observations about skin response and temperature."""
    notes = []
    skin = comparison["skin_response_change_pct"]
    if skin is not None and skin >= SKIN_RESPONSE_NOTABLE_CHANGE:
        notes.append(f"skin response is {skin}% above baseline (sweating or arousal)")
    temp = comparison["temperature_change"]
    if temp is not None and abs(temp) >= TEMPERATURE_NOTABLE_CHANGE:
        direction = "above" if temp > 0 else "below"
        notes.append(f"skin temperature is {abs(temp)} C {direction} baseline")
    return notes


def format_value(value, unit="", decimals=1):
    """Format a number for the report, showing '-' for missing values."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{decimals}f}{unit}"
    return f"{value}{unit}"


def format_report(result):
    """Turn the dictionary produced by ``TrainingSession.analyze`` into text."""
    counts = result["counts"]
    comp = result["comparison"]
    lines = [
        "=" * 70,
        f"Session {result['session_id']} - {result['participant']['name']} "
        f"({result['participant']['participant_id']})",
        "=" * 70,
        f"Source         : {', '.join(result['source_files']) or '-'}",
        f"Classification : {result['classification'].upper()} ({result['status']})",
        f"Windows        : {counts['received']} received, {counts['usable']} usable "
        f"({counts['valid']} valid, {counts['flagged']} flagged), {counts['excluded']} excluded",
        "",
        f"{'Measurement':<16}{'n':>4}{'mean':>10}{'median':>10}{'min':>10}{'max':>10}",
    ]
    for name, stats in result["summaries"].items():
        lines.append(f"{name:<16}{stats['count']:>4}{format_value(stats['mean'], decimals=2):>10}"
                     f"{format_value(stats['median'], decimals=2):>10}"
                     f"{format_value(stats['min'], decimals=2):>10}"
                     f"{format_value(stats['max'], decimals=2):>10}")

    lines += [
        "",
        "Compared with personal reference:",
        f"  mean HR above resting : {format_value(comp['mean_hr_above_resting'], ' bpm')}",
        f"  HR reserve mean/median/peak: {format_value(comp['mean_hrr_pct'], '%')} / "
        f"{format_value(comp['median_hrr_pct'], '%')} / {format_value(comp['peak_hrr_pct'], '%')}",
        f"  skin response change  : {format_value(comp['skin_response_change_pct'], '%')}",
        f"  temperature change    : {format_value(comp['temperature_change'], ' C', 2)}",
        "",
        f"Recovery: {'yes' if result['recovery']['detected'] else 'no'} - {result['recovery']['reason']}",
        "",
        "Why:",
    ]
    lines += [f"  - {reason}" for reason in result["explanation"]]
    if result["unusual"]:
        lines += ["", "Unusual:"]
        lines += [f"  - {finding}" for finding in result["unusual"]]
    if result["issues"]:
        lines += ["", "Data quality issues:"]
        lines += [f"  - t={issue['timestamp']} ({issue['source'] or 'no source'}): "
                  f"[{issue['status']}] {issue['message']}"
                  for issue in result["issues"]]
    return "\n".join(lines)
