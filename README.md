# Smart Fitness Session Analyzer

**Selected option:** Option A: Smart Fitness Session Analyzer

**Student name:** Nikolai Fjeld Hansen 
**Student number:** 403201 

## Description

A console program that analyzes simulated wearable-device data from training
sessions. For each session it:

1. builds a participant with personal reference values (resting heart rate, estimated maximum heart rate, baseline skin response and temperature)
2. validates every observation window and marks it **valid**, **flagged** (usable with a warning) or **rejected** (excluded);
3. calculates summaries (count, mean, median, min, max) for every measurement
4. compares the session with the participant's reference values
5. checks whether heart rate and activity fall near the end (recovery)
6. classifies the session as *resting*, *moderate activity*, *high acivity*,
   *recovering* or *insuficient dta*, and explains why; and
7. returns everything as a dictionary and prints a readable report.

## Files

```
main.py            runs all the scenarios and prints the reports
models.py          the classes
analysis.py        the standalone functions (calculations, classification, report)
sample_data.py     the 8 scenarios (5 from the generator + 3 I made myself)
data_generator.py  the generator we got for Option A (not changed)
tests.py           tests
requirements.txt   empty, only standard library
```

I split it into `models.py` and `analysis.py` so the calculations are just normal functions that are easy to test without making objects.

## Classes

- `ReferenceProfile` - the participant's baseline values (resting HR, max HR, skin response, temperature)
- `Participant` - a person, has a `ReferenceProfile`
- `RangeRule` - checks that a value exists, is a number and is inside a range. returns ok, flag or reject
- `SignalQualityRule` - subclass of `RangeRule`, rejects signal quality under 0.5 and flags under 0.7
- `Observation` - one window of data, validates itself when it's created
- `TrainingSession` - a participant + a list of observations. `analyze()` returns the result as a dict

### OOP stuff

- **Composition:** `TrainingSession` has a `Participant` and a list of `Observation`s, and `Participant` has a `ReferenceProfile`
- **Encapsulation:** `participant_id` is read only (property), `reference` has a setter that only accepts a `ReferenceProfile`. `Observation` keeps its status and issues private and you can only change them with `flag()` and `reject()`. The session gives out its observations as a tuple so you have to use `add_observation()` which runs the checks
- **Inheritance/overriding:** `SignalQualityRule` overrides `check()`. It calls `super().check()` first for the normal range check and then adds the quality limits. Signal quality is a range rule with extra rules so inheritance made sense here, the rest is "has a" so I used composition there
- **Class/static method:** `ReferenceProfile.from_generator_profile()` is a classmethod that makes a profile from the generator's dict. `estimate_max_heart_rate()` is a staticmethod because it's just a formula and doesn't need an object
- **Functions:** `summarize`, `heart_rate_reserve_percent`, `compare_with_reference`, `detect_recovery`, `classify_session`, `describe_physiology`, `format_value`, `format_report`

## Assumptions and rules

**Validation**

- timestamp has to be 0 or more and go up, duplicates get rejected
- heart rate is required, 30-220 bpm
- activity level is required, 0-1
- skin response and temperature are optional, if they're missing the window just gets flagged
- signal quality under 0.5 = rejected, under 0.7 = flagged
- heart rate over the estimated max gets flagged
- text, booleans, NaN and records that aren't dicts get rejected

Flagged windows are still used, rejected ones are just counted and listed in the report.

**Heart rate.** The generator only gives resting heart rate, so I estimate max HR from age with the Tanaka formula (208 - 0.7 * age). The ages are set in `sample_data.py`, default is 35. Then I use % of heart rate reserve: `(HR - resting) / (max - resting) * 100` so people with different fitness can be compared.

**Classification** (checked in this order)

1. **insufficient data** - less than 4 usable windows or less than half the windows usable
2. **recovering** - at least 6 windows, and comparing the last third with the rest: peak effort was at least 40% HRR, HR dropped 15+ bpm, activity dropped 0.2+, and HR is still going down at the end
3. otherwise based on the median % HRR (median so one weird spike doesn't change it):
   - under 15% = resting
   - 15-40% = moderate activity
   - 40%+ = high activity

I picked the thresholds by testing against the generator, they're not from any medical source. I ran 500 seeds per scenario and got basically 99-100% right (recovery drops to ~91% with only 8 windows).

The report also adds a note if HR is high but you're barely moving (stress, heat, sensor fault?), if skin response is 50%+ over baseline, or if temperature is 1 C+ off baseline.

## How to run

No packages needed, only standard library (Python 3.8+), so no venv.

```bash
git clone https://github.com/NIKO-EDU/python_acit4420_fitness.git
cd python_acit4420_fitness
python3 main.py
```

On Windows use `python` instead of `python3`. You can also do `python3 main.py --json` to get the result dicts as JSON, and `python3 tests.py` to run the tests.

## Example output

Recovery scenario + the summary at the end:

```
Scenario: recovery
======================================================================
Session S04 - Jonas (P004)
======================================================================
Classification : RECOVERING
Windows        : 12 received, 12 usable (12 valid, 0 flagged), 0 rejected

Measurement        n      mean    median       min       max
heart_rate        12    106.67    107.00        75       137
skin_response     12      2.17      2.17      1.81      2.39
temperature       12     32.96     32.95     32.79     33.25
activity_level    12      0.48      0.48      0.06      0.88
signal_quality    12      0.92      0.92      0.87      0.99

Compared with personal reference:
  mean HR above resting : 35.7 bpm
  HR reserve mean/median/peak: 31.7% / 32.0% / 58.7%
  skin response change  : 21.9%
  temperature change    : 0.27 C

Recovery: yes - peak effort 58.7% HRR (need >= 40.0%); heart rate fell 30.6 bpm in final 4 windows (need >= 15.0); activity fell 0.44 (need >= 0.2); heart rate still falling across the final windows

...

======================================================================
SUMMARY
======================================================================
S01  resting                              resting            12/12 usable
S02  moderate activity                    moderate activity  12/12 usable
S03  high activity                        high activity      12/12 usable
S04  recovery                             recovering         12/12 usable
S05  poor quality                         insufficient data  0/12 usable
S06  raised heart rate without movement   moderate activity  8/8 usable
S07  mixed quality with invalid records   moderate activity  6/10 usable
S08  too few windows                      insufficient data  3/3 usable
```

S01-S05 are the 5 required ones from the generator. S06-S08 are extra ones I made: high heart rate without moving, a session with a bunch of broken records mixed in, and one that's too short.

## Limitations

- max HR is just an estimate from age, real max can be 10-15 bpm off
- the thresholds are tuned for the fake data, not tested on real people
- recovery detection needs 6+ windows and is less reliable on short sessions
- one label per session, so something like interval training just gets the median
- skin response and temperature only add notes, they don't change the label
- timestamps are just treated as order, gaps aren't detected
