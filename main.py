import json
import sys

from analysis import format_report
from models import Participant, ReferenceProfile, TrainingSession
from sample_data import all_scenarios


def build_session(scenario):
    """Turn one scenario dictionary into a TrainingSession object."""
    info = scenario["participant"]
    reference = ReferenceProfile.from_generator_profile(info["profile"], age=info["age"])
    participant = Participant(info["profile"]["participant_id"], reference,
                              name=info["name"], age=info["age"])
    return TrainingSession(scenario["session_id"], participant, scenario["observations"])


def run_all():
    """Analyze every scenario and return ``[(title, result_dict), ...]``."""
    return [(s["title"], build_session(s).analyze()) for s in all_scenarios()]


def main(argv):
    results = run_all()
    if "--json" in argv:
        print(json.dumps([r for _, r in results], indent=2))
        return

    for title, result in results:
        print(f"\nScenario: {title}")
        print(format_report(result))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for title, result in results:
        c = result["counts"]
        print(f"{result['session_id']}  {title:<36} {result['classification']:<18} "
              f"{c['usable']}/{c['received']} usable")


if __name__ == "__main__":
    main(sys.argv[1:])
