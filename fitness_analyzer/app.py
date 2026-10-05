"""Ties the loader, the sessions and the report writer together."""

from dataclasses import dataclass, field

from .exceptions import DataFileError
from .loader import DataLoader
from .reports import ReportWriter


@dataclass
class RunSummary:
    accepted_rows: int
    rejected_rows: int
    results: list
    created_files: list
    file_errors: list = field(default_factory=list)


class FitnessAnalyzerApp:
    def __init__(self, profiles_path, session_paths, output_dir):
        self.profiles_path = profiles_path
        self.session_paths = list(session_paths)
        self.loader = DataLoader()
        self.writer = ReportWriter(output_dir)

    def run(self):
        """Load, analyze and write the reports.

        A broken profile file stops the run (the DataFileError goes to the
        caller), because no session can be checked without it. A broken
        session file is noted and skipped, and the other files still run.
        """
        self.loader.load_participants(self.profiles_path)

        file_errors = []
        for path in self.session_paths:
            try:
                self.loader.load_sessions(path)
            except DataFileError as error:
                file_errors.append(str(error))

        sessions = self.loader.sessions
        results = [sessions[session_id].analyze() for session_id in sorted(sessions)]
        inputs = [str(self.profiles_path), *(str(p) for p in self.session_paths)]
        created = self.writer.write_all(results, self.loader.rejected, file_errors, inputs)
        return RunSummary(
            accepted_rows=self.loader.accepted_rows,
            rejected_rows=len(self.loader.rejected),
            results=results,
            created_files=created,
            file_errors=file_errors,
        )
