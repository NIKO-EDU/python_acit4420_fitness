"""Writing the output files.

The files are overwritten every time and contain no dates or times, so
running the program twice on the same input gives exactly the same output.
"""

import csv

from .analysis import format_report

SUMMARY_FILE = "analysis_summary.csv"
REPORT_FILE = "analysis_report.txt"
REJECTED_FILE = "rejected_records.txt"

SUMMARY_COLUMNS = (
    "session_id", "participant_id", "participant_name", "source_files",
    "received", "usable", "valid", "flagged", "excluded",
    "mean_heart_rate", "median_heart_rate", "max_heart_rate",
    "resting_heart_rate", "estimated_max_heart_rate",
    "mean_hr_above_resting", "median_hrr_pct", "peak_hrr_pct",
    "mean_activity", "skin_response_change_pct", "temperature_change",
    "recovery_detected", "classification", "status", "explanation", "unusual",
)


def summary_row(result):
    """Flatten one result dictionary into a row for analysis_summary.csv."""
    counts = result["counts"]
    hr = result["summaries"]["heart_rate"]
    comp = result["comparison"]
    return {
        "session_id": result["session_id"],
        "participant_id": result["participant"]["participant_id"],
        "participant_name": result["participant"]["name"],
        "source_files": ";".join(result["source_files"]),
        **{key: counts[key] for key in ("received", "usable", "valid", "flagged", "excluded")},
        "mean_heart_rate": hr["mean"],
        "median_heart_rate": hr["median"],
        "max_heart_rate": hr["max"],
        "resting_heart_rate": result["reference"]["resting_heart_rate"],
        "estimated_max_heart_rate": result["reference"]["max_heart_rate"],
        "mean_hr_above_resting": comp["mean_hr_above_resting"],
        "median_hrr_pct": comp["median_hrr_pct"],
        "peak_hrr_pct": comp["peak_hrr_pct"],
        "mean_activity": result["summaries"]["activity_level"]["mean"],
        "skin_response_change_pct": comp["skin_response_change_pct"],
        "temperature_change": comp["temperature_change"],
        "recovery_detected": result["recovery"]["detected"],
        "classification": result["classification"],
        "status": result["status"],
        "explanation": " | ".join(result["explanation"]),
        "unusual": " | ".join(result["unusual"]),
    }


class ReportWriter:
    def __init__(self, output_dir):
        self.output_dir = output_dir

    def write_all(self, results, rejected, file_errors, inputs):
        """Write the three report files and return their paths."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return [
            self.write_summary(results),
            self.write_report(results, inputs),
            self.write_rejected(results, rejected, file_errors),
        ]

    def write_summary(self, results):
        path = self.output_dir / SUMMARY_FILE
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
            writer.writeheader()
            for result in results:
                row = summary_row(result)
                writer.writerow({key: "" if value is None else value for key, value in row.items()})
        return path

    def write_report(self, results, inputs):
        path = self.output_dir / REPORT_FILE
        lines = [
            "SMART FITNESS SESSION ANALYSIS",
            "Input files: " + ", ".join(inputs),
            "Max heart rate is estimated with the Tanaka formula and age 35, because the",
            "profile file has no age. Windows with signal quality below 0.5 are excluded.",
            "",
        ]
        for result in results:
            lines += [format_report(result), ""]

        lines += ["=" * 70, "SUMMARY", "=" * 70]
        for result in results:
            c = result["counts"]
            lines.append(f"{result['session_id']}  {result['participant']['name']:<12} "
                         f"{result['classification']:<18} {result['status']:<18} "
                         f"{c['usable']}/{c['received']} usable")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def write_rejected(self, results, rejected, file_errors):
        path = self.output_dir / REJECTED_FILE
        lines = ["REJECTED RECORDS", "=" * 70]
        if file_errors:
            lines.append("Files that could not be processed:")
            lines += [f"  - {error}" for error in file_errors]
            lines.append("")

        lines += [f"Rejected rows: {len(rejected)} (not used anywhere)", ""]
        for record in rejected:
            lines.append(f"{record.source_file}, row {record.row_number}: {','.join(record.raw_row)}")
            lines += [f"  - field {field or '(row)'}: {reason}" for field, reason in record.issues]

        excluded = [(result["session_id"], issue) for result in results
                    for issue in result["issues"] if issue["status"] == "excluded"]
        lines += ["", f"Accepted rows excluded from analysis because of poor signal: {len(excluded)}", ""]
        for session_id, issue in excluded:
            lines.append(f"{issue['source']} ({session_id}, t={issue['timestamp']}): {issue['message']}")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
