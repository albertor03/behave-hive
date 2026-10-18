"""User-facing errors. The CLI prints them without a traceback."""

from __future__ import annotations

from pathlib import Path


class HiveError(Exception):
    """Base class for errors reported to the user."""

    exit_code = 2


class ConfigError(HiveError):
    """Invalid or incompatible configuration."""


class CsvExamplesError(HiveError):
    """A problem with a CSV reference in a feature or with the CSV itself."""

    def __init__(
        self,
        message: str,
        *,
        feature: Path | None = None,
        line: int | None = None,
        csv_path: Path | None = None,
        csv_row: int | None = None,
    ) -> None:
        self.feature = feature
        self.line = line
        self.csv_path = csv_path
        self.csv_row = csv_row
        where = []
        if feature is not None:
            where.append(f"{feature}" + (f", line {line}" if line is not None else ""))
        if csv_path is not None:
            where.append(f"{csv_path}" + (f", row {csv_row}" if csv_row is not None else ""))
        super().__init__(f"{message} ({'; '.join(where)})" if where else message)
