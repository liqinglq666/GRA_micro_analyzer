# core/exceptions.py
"""
GRA-MicroAnalyzer — Custom Exception Hierarchy
===============================================
All application exceptions inherit from GRABaseException so that
the UI boundary layer needs only one broad `except GRABaseException`
clause, while still being able to branch on specific subtypes.
"""

from __future__ import annotations

import math


class GRABaseException(Exception):
    """Root of the GRA-MicroAnalyzer exception tree."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r})"


# ---------------------------------------------------------------------------
# I/O Exceptions
# ---------------------------------------------------------------------------


class DataLoadError(GRABaseException):
    """Raised when a file cannot be read from disk or is structurally unusable."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to load dataset from '{path}': {reason}")


class UnsupportedFileFormatError(GRABaseException):
    """Raised when the selected file extension is not supported."""

    def __init__(self, suffix: str, supported: tuple[str, ...]) -> None:
        self.suffix = suffix
        self.supported = supported
        supported_str = ", ".join(supported)
        super().__init__(
            f"File format '{suffix}' is not supported. Accepted formats: {supported_str}."
        )


# ---------------------------------------------------------------------------
# Configuration / Validation Exceptions
# ---------------------------------------------------------------------------


class InsufficientDataError(GRABaseException):
    """Raised when the dataset has too few usable rows for GRA."""

    def __init__(self, row_count: int, minimum_required: int = 2) -> None:
        self.row_count = row_count
        self.minimum_required = minimum_required
        super().__init__(
            f"Dataset contains only {row_count} usable data row(s); "
            f"at least {minimum_required} samples are required for GRA."
        )


class ColumnNotFoundError(GRABaseException):
    """Raised when a configured column does not exist in the loaded DataFrame."""

    def __init__(self, column_name: str, available_columns: list[str]) -> None:
        self.column_name = column_name
        self.available_columns = available_columns
        super().__init__(
            f"Column '{column_name}' was not found in the dataset. "
            f"Available columns: {available_columns}."
        )


class PolarityConfigError(GRABaseException):
    """Raised when polarity mapping is incomplete."""

    def __init__(self, missing_columns: list[str]) -> None:
        self.missing_columns = missing_columns
        super().__init__(
            f"Polarity not defined for the following comparative column(s): {missing_columns}. "
            "Every comparative sequence must be assigned either 'LTB' or 'STB'."
        )


class DuplicateColumnError(GRABaseException):
    """Raised when reference and comparative sequence refer to the same column."""

    def __init__(self, column_name: str) -> None:
        self.column_name = column_name
        super().__init__(
            f"Column '{column_name}' cannot serve as both the reference sequence "
            "and a comparative sequence simultaneously."
        )


# ---------------------------------------------------------------------------
# Computation Exceptions
# ---------------------------------------------------------------------------


class NormalizationError(GRABaseException):
    """Raised when a column cannot be normalised because its range is zero."""

    def __init__(self, column_name: str, constant_value: float) -> None:
        self.column_name = column_name
        self.constant_value = constant_value
        if isinstance(constant_value, float) and math.isnan(constant_value):
            detail = "all retained comparative factors are constant or unusable"
        else:
            detail = f"all values are identical ({constant_value})"
        super().__init__(
            f"Cannot normalise column '{column_name}': {detail}. "
            "A constant sequence carries no discriminatory information."
        )


class ComputationError(GRABaseException):
    """Raised for unexpected numerical failures during the GRA pipeline."""

    def __init__(self, stage: str, detail: str) -> None:
        self.stage = stage
        self.detail = detail
        super().__init__(f"Computation failed at stage '{stage}': {detail}")
