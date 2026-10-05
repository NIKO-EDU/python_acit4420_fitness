# Smart Fitness Session Analyzer

**Selected option:** Option A: Smart Fitness Session Analyzer (Assignment II, continued from Assignment I)

**Student name:** Nikolai Fjeld Hansen
**Student number:** 403201

## Description

In Assignment I the program analyzed simulated sessions from the data generator. Assignment II builds on the same classes and analysis, but the data now comes from CSV files. For each run it:

1. loads the participant profiles and the session files with the `csv` module;
2. checks the identifiers with regular expressions, converts the values to numbers and rejects rows that can't be used, logging the file, row, field and reason for each one;
3. groups the rows into sessions by `session_id` and connects each session to its participant;
4. analyzes every session the same way as in A1: summaries, comparison with the personal baseline, recovery check and classification;
5. gives each session an overall status: **normal**, **unusual** or **insufficient data**;
6. writes `analysis_summary.csv`, `analysis_report.txt` and `rejected_records.txt` to the output folder.

## How to run

Only the standard library is needed (Python 3.8+). Run it from the repository root:

```bash
python3 main.py --profiles data/participants.csv \
    --sessions data/fitness_sessions.csv data/fitness_sessions_invalid.csv \
    --output output
```

Every argument has a default, so plain `python3 main.py` does the same thing. The output folder is created if it doesn't exist. The files are overwritten on every run and contain no timestamps, so running it again gives the same output. `--json` also prints the result dictionaries.

```
Analysis complete.
  Accepted rows    : 30
  Rejected rows    : 10
  Sessions analyzed: 6
  Created files:
    output/analysis_summary.csv
    output/analysis_report.txt
    output/rejected_records.txt
```

Tests: `python3 -m unittest -v`

## Files

```
main.py                       command line (argparse), prints the completion summary
fitness_analyzer/
    models.py                 the classes from A1 (ReferenceProfile, Participant, RangeRule,
                              SignalQualityRule, Observation, TrainingSession)
    analysis.py               the functions from A1 (summaries, HRR, recovery, classification, report)
    validation.py             regex checks for the IDs and file names, CSV text -> numbers
    exceptions.py             custom exceptions
    loader.py                 reads the CSV files and builds participants and sessions
    reports.py                writes the three output files
    app.py                    ties the loader, the sessions and the report writer together
data/                         the official CSV files (not changed)
tests/                        unittest tests
data_generator.py             the A1 generator, now only used by a test that checks the thresholds
```

## What changed from Assignment I

- **Package:** `models.py` and `analysis.py` moved into `fitness_analyzer/`, and new modules were added for loading, validation, exceptions and reports. `sample_data.py` was removed because the data now comes from CSV.
- **Validation:**
  - `RangeRule.check()` now raises `InvalidRecordError` for impossible values, so the whole row gets rejected.
  - The new `assess()` method decides whether a valid value is ok, flagged or excluded.
  - `SignalQualityRule` overrides `assess()`, the same way it overrode `check()` before.
  - `Observation` collects every problem in a row before raising, so the report shows all of them at once.
- **Identifiers:** `Participant` and `TrainingSession` validate their IDs with regex (`^P\d{3}$` and `^FIT-\d{4}-\d{3}$`) and raise `InvalidIdentifierError`.
- **Rejected vs excluded:** a *rejected* row is invalid and isn't used anywhere. An *excluded* window is a valid row with poor signal: it is counted in the session but not used in the calculations. Duplicate or out-of-order timestamps now reject the row.
- **Normal vs unusual:**
  - The "notes" from A1 are now a separate function, `find_unusual_patterns()`, and `session_status()` turns the result into normal, unusual or insufficient data.
  - Raised heart rate while barely moving counts as unusual. So does movement with no heart-rate response.
  - Raised skin response or temperature only counts as unusual at rest; during exercise it's expected.
- **Profiles:** `ReferenceProfile.from_generator_profile` became `from_profile` and works with a CSV row. The CSV has no age, so max HR uses the default age of 35.
- **Fixed:** the recovery explanation printed "heart rate still falling" even when that check had failed.

## Rules

**Validation (a broken rule rejects the row)**

| Field | Rule |
|---|---|
| row | exactly 8 fields (5 in the profile file) |
| `session_id` | `FIT-YYYY-NNN`, full match |
| `participant_id` | `P` + 3 digits, full match, and must be in `participants.csv` |
| `timestamp` | whole number, 0 or more, increasing within a session |
| `heart_rate` | required, 30-220 bpm |
| `activity_level` | required, 0-1 |
| `skin_response` | optional, 0-30 (missing = flagged) |
| `temperature` | optional, 20-42 C (missing = flagged) |
| `signal_quality` | required, 0-1 |
| profile | name required, baseline HR 30-120, skin response above 0, temperature 25-40 |

All the ranges include both ends. Text that isn't a number, NaN and infinity are rejected. A session keeps the participant from its first row, so a later row with another participant is rejected.

**Signal quality (a data-quality issue, not an invalid row)**: below 0.5 the window is excluded from the analysis, and below 0.7 it is flagged but still used. Excluded windows are listed in their session in the report and in their own section of `rejected_records.txt`.

**Classification** (same as A1, checked in this order)

1. **insufficient data**: fewer than 4 usable windows, or less than half the windows usable.
2. **recovering**: at least 6 windows, and when the last third is compared with the rest, peak effort was at least 40% HRR, HR dropped 15+ bpm, activity dropped 0.2+, and HR is still going down at the end.
3. Otherwise it is based on the median % of heart-rate reserve: under 15% = resting, 15-40% = moderate activity, 40%+ = high activity.

Max HR is estimated with the Tanaka formula (208 - 0.7 × age, using age 35), and HRR % = (HR - resting) / (max - resting) × 100.

**Status**: insufficient data if the label is insufficient data, unusual if `find_unusual_patterns()` found anything, and normal otherwise.

## Error handling

- `InvalidIdentifierError`, `InvalidRecordError` and `UnknownParticipantError` cover problems in a single row. They are all `ValueError`s and carry a list of `(field, reason)` pairs. The loader catches them for each row, logs the row and moves on to the next one.
- `UnknownParticipantError` is raised when looking up the participant gives a `KeyError`.
- `DataFileError` covers a whole file. `FileNotFoundError`, `PermissionError`, `IsADirectoryError`, `UnicodeDecodeError` and `csv.Error` are caught where the file is opened and raised again with the file name. A wrong or empty header is also a `DataFileError`.
- A broken session file is listed in `rejected_records.txt` and the other files still run. A broken profile file stops the program with exit code 1, because no session can be checked without it.
- There is no bare `except` and no `except Exception`.

## Results on the official data

```
FIT-2026-001  Amina Noor   resting            normal             6/6 usable
FIT-2026-002  Jonas Berg   moderate activity  normal             6/6 usable
FIT-2026-003  Maya Chen    high activity      normal             6/6 usable
FIT-2026-004  Amina Noor   recovering         normal             6/6 usable
FIT-2026-005  Jonas Berg   insufficient data  insufficient data  0/5 usable
FIT-2026-101  Amina Noor   insufficient data  insufficient data  1/1 usable
```

10 of the 11 rows in `fitness_sessions_invalid.csv` are rejected. FIT-2026-005 is valid data, but every window has signal quality below 0.5. FIT-2026-101 only has one valid row left. The FIT-2026-102 rows are all rejected, so that session doesn't appear.

## Limitations

- max HR is only an estimate, and since the CSV has no age everyone gets age 35
- the thresholds were tuned on the simulated data, not on real people
- the official sessions are short (5-6 windows), which is only just enough for the recovery check
- each session gets one label, so something like interval training just gets the median
- timestamps are only treated as order, gaps aren't detected
