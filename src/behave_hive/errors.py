"""User-facing errors. The CLI prints them without a traceback."""

from __future__ import annotations

from pathlib import Path


class HiveError(Exception):
    """Base class for errors reported to the user."""

    exit_code = 2


class ConfigError(HiveError):
    """Invalid or incompatible configuration."""


class ExamplesDataError(HiveError):
    """A problem with a CSV or JSON reference in a feature or with the data file itself."""

    def __init__(
        self,
        message: str,
        *,
        feature: Path | None = None,
        line: int | None = None,
        data_path: Path | None = None,
        data_row: int | None = None,
    ) -> None:
        self.feature = feature
        self.line = line
        self.data_path = data_path
        self.data_row = data_row
        where = []
        if feature is not None:
            where.append(f"{feature}" + (f", line {line}" if line is not None else ""))
        if data_path is not None:
            where.append(f"{data_path}" + (f", row {data_row}" if data_row is not None else ""))
        super().__init__(f"{message} ({'; '.join(where)})" if where else message)


CsvExamplesError = ExamplesDataError
