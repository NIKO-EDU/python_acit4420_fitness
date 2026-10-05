"""Run the analyzer from the repository root.

    python3 main.py --profiles data/participants.csv \
        --sessions data/fitness_sessions.csv data/fitness_sessions_invalid.csv --output output
"""

import argparse
import json
import sys
from pathlib import Path

from fitness_analyzer.app import FitnessAnalyzerApp
from fitness_analyzer.exceptions import DataFileError

DATA_DIR = Path("data")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Analyze wearable fitness sessions from CSV files.")
    parser.add_argument("--profiles", type=Path, default=DATA_DIR / "participants.csv",
                        help="participant profile CSV (default: %(default)s)")
    parser.add_argument("--sessions", type=Path, nargs="+",
                        default=[DATA_DIR / "fitness_sessions.csv", DATA_DIR / "fitness_sessions_invalid.csv"],
                        help="one or more session CSV files (default: the valid and the invalid file)")
    parser.add_argument("--output", type=Path, default=Path("output"),
                        help="folder for the reports, created if missing (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="also print the result dictionaries as JSON")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    app = FitnessAnalyzerApp(args.profiles, args.sessions, args.output)
    try:
        summary = app.run()
    except DataFileError as error:
        print(f"Error: cannot use the profile file - {error}", file=sys.stderr)
        return 1
    except PermissionError as error:
        print(f"Error: cannot write the reports to {args.output}: {error.strerror}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary.results, indent=2))

    print("Analysis complete.")
    print(f"  Accepted rows    : {summary.accepted_rows}")
    print(f"  Rejected rows    : {summary.rejected_rows}")
    print(f"  Sessions analyzed: {len(summary.results)}")
    for error in summary.file_errors:
        print(f"  Skipped file     : {error}")
    print("  Created files:")
    for path in summary.created_files:
        print(f"    {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
