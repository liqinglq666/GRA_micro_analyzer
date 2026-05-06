# core/exceptions.py
"""
GRA-MicroAnalyzer — Custom Exception Hierarchy
===============================================
All application exceptions inherit from GRABaseException so that
the UI boundary layer needs only one broad `except GRABaseException`
clause, while still being able to branch on specific subtypes.

Each exception carries structured attributes in addition to the
human-readable `message` string, enabling programmatic inspection
without string-parsing.
"""

from __future__ import annotations


class GRABaseException(Exception):
    """
    Root of the GRA-MicroAnalyzer exception tree.

    Parameters
    ----------
    message:
        A human-readable description suitable for display in a
        QMessageBox or log entry.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message: str = message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r})"


# ---------------------------------------------------------------------------
# I/O Exceptions
# ---------------------------------------------------------------------------


class DataLoadError(GRABaseException):
    """
    Raised when a file cannot be read from disk or is structurally
    unusable (empty, corrupt, wrong format).

    Parameters
    ----------
    path:
        The filesystem path that was attempted.
    reason:
        A short technical description of the root cause, e.g.
        'File not found' or 'Sheet contains no tabular data'.
    """

    def __init__(self, path: str, reason: str) -> None:
        self.path: str = path
        self.reason: str = reason
        super().__init__(
            f"Failed to load dataset from '{path}': {reason}"
        )


class UnsupportedFileFormatError(GRABaseException):
    """
    Raised when the user selects a file whose extension is not among
    the supported formats (.csv, .xlsx, .xls).

    Parameters
    ----------
    suffix:
        The unsupported file extension that was encountered.
    supported:
        Tuple of supported extensions for inclusion in the error message.
    """

    def __init__(self, suffix: str, supported: tuple[str, ...]) -> None:
        self.suffix: str = suffix
        self.supported: tuple[str, ...] = supported
        supported_str = ", ".join(supported)
        super().__init__(
            f"File format '{suffix}' is not supported. "
            f"Accepted formats: {supported_str}."
        )


# ---------------------------------------------------------------------------
# Configuration / Validation Exceptions
# ---------------------------------------------------------------------------


class InsufficientDataError(GRABaseException):
    """
    Raised when the dataset has too few rows to produce a meaningful
    GRA result (minimum: 2 samples).

    Parameters
    ----------
    row_count:
        The number of data rows actually present.
    minimum_required:
        The minimum number of rows the engine requires.
    """

    def __init__(self, row_count: int, minimum_required: int = 2) -> None:
        self.row_count: int = row_count
        self.minimum_required: int = minimum_required
        super().__init__(
            f"Dataset contains only {row_count} data row(s); "
            f"at least {minimum_required} samples are required for GRA."
        )


class ColumnNotFoundError(GRABaseException):
    """
    Raised when a column name specified in the configuration does not
    exist in the loaded DataFrame.

    Parameters
    ----------
    column_name:
        The missing column identifier.
    available_columns:
        The list of columns actually present in the DataFrame.
    """

    def __init__(self, column_name: str, available_columns: list[str]) -> None:
        self.column_name: str = column_name
        self.available_columns: list[str] = available_columns
        super().__init__(
            f"Column '{column_name}' was not found in the dataset. "
            f"Available columns: {available_columns}."
        )


class PolarityConfigError(GRABaseException):
    """
    Raised when the polarity mapping is missing for one or more
    comparative columns or contains an unrecognised polarity value.

    Parameters
    ----------
    missing_columns:
        The list of comparative column names that lack a polarity entry.
    """

    def __init__(self, missing_columns: list[str]) -> None:
        self.missing_columns: list[str] = missing_columns
        super().__init__(
            f"Polarity not defined for the following comparative "
            f"column(s): {missing_columns}. Every comparative sequence "
            f"must be assigned either 'LTB' (Larger-is-Better) or "
            f"'STB' (Smaller-is-Better)."
        )


class DuplicateColumnError(GRABaseException):
    """
    Raised when the reference sequence and a comparative sequence
    refer to the same column, which would produce a trivial (all-ones)
    relational coefficient vector.

    Parameters
    ----------
    column_name:
        The column name that appears in both roles.
    """

    def __init__(self, column_name: str) -> None:
        self.column_name: str = column_name
        super().__init__(
            f"Column '{column_name}' cannot serve as both the reference "
            f"sequence and a comparative sequence simultaneously."
        )


# ---------------------------------------------------------------------------
# Computation Exceptions
# ---------------------------------------------------------------------------


class NormalizationError(GRABaseException):
    """
    Raised when a column cannot be normalised because its range is zero
    (all values are identical), which would cause a division-by-zero.

    Parameters
    ----------
    column_name:
        The column whose values are constant.
    constant_value:
        The single value present throughout the column.
    """

    def __init__(self, column_name: str, constant_value: float) -> None:
        self.column_name: str = column_name
        self.constant_value: float = constant_value
        super().__init__(
            f"Cannot normalise column '{column_name}': all {row_count_placeholder} "
            f"values are identical ({constant_value}). "
            f"A constant sequence carries no discriminatory information."
        )

    def __init__(self, column_name: str, constant_value: float) -> None:  # type: ignore[no-redef]
        self.column_name: str = column_name
        self.constant_value: float = constant_value
        super().__init__(
            f"Cannot normalise column '{column_name}': all values are "
            f"identical ({constant_value}). "
            f"A constant sequence carries no discriminatory information."
        )


class ComputationError(GRABaseException):
    """
    Raised for any unexpected numerical failure during the GRA pipeline
    that is not covered by a more specific exception (e.g. NaN
    propagation from upstream data quality issues).

    Parameters
    ----------
    stage:
        The pipeline stage where the failure occurred, e.g.
        'normalization', 'relational_coefficient', 'grading'.
    detail:
        A technical description of the failure, typically the str()
        of the caught underlying exception.
    """

    def __init__(self, stage: str, detail: str) -> None:
        self.stage: str = stage
        self.detail: str = detail
        super().__init__(
            f"Computation failed at stage '{stage}': {detail}"
        )
