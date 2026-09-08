"""Input validation, cleaning, and effective-configuration preparation for GRA."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from core.constants import EPSILON, MINIMUM_SAMPLES, SMALL_SAMPLE_WARNING
from core.data_model import ColumnConfig, DataQualityReport, GRAConfig
from core.exceptions import (
    ColumnNotFoundError,
    InsufficientDataError,
    NormalizationError,
    PolarityConfigError,
)

logger = logging.getLogger(__name__)


def prepare_analysis_data(
    dataframe: pd.DataFrame,
    config: GRAConfig,
) -> tuple[pd.DataFrame, GRAConfig, DataQualityReport]:
    """Validate and clean the input data without changing existing GRA semantics."""
    required_columns = [
        config.id_column,
        config.reference_column,
        *config.comparative_column_names,
    ]
    assert_columns_exist(dataframe, required_columns)
    assert_polarity_completeness(config)

    unique_columns = list(dict.fromkeys(required_columns))
    subset = dataframe[unique_columns].copy()
    numeric_columns = [
        config.reference_column,
        *config.comparative_column_names,
    ]

    original_rows = len(subset)
    conversion_failures: dict[str, int] = {}
    non_finite_values: dict[str, int] = {}

    for column in numeric_columns:
        original_non_empty = subset[column].notna() & (
            subset[column].astype(str).str.strip() != ""
        )
        coerced = pd.to_numeric(subset[column], errors="coerce")

        failed = int((original_non_empty & coerced.isna()).sum())
        if failed:
            conversion_failures[column] = failed

        numeric_array = coerced.to_numpy(dtype=float, na_value=np.nan)
        inf_count = int(np.isinf(numeric_array).sum())
        if inf_count:
            non_finite_values[column] = inf_count

        subset[column] = coerced.replace([np.inf, -np.inf], np.nan)

    _log_quality_warnings(conversion_failures, non_finite_values)

    subset = subset.dropna(subset=numeric_columns)
    dropped_rows = original_rows - len(subset)
    if dropped_rows > 0:
        logger.warning(
            "%d row(s) dropped due to missing, non-numeric, or non-finite values in analysis columns.",
            dropped_rows,
        )

    if len(subset) < MINIMUM_SAMPLES:
        raise InsufficientDataError(
            row_count=len(subset),
            minimum_required=MINIMUM_SAMPLES,
        )

    warnings = _small_sample_warnings(len(subset))
    assert_reference_not_constant(subset, config.reference_column)
    effective_config = drop_constant_comparative_factors(subset, config)
    dropped_constant_factors = [
        name
        for name in config.comparative_column_names
        if name not in effective_config.comparative_columns
    ]

    kept_columns = [
        config.id_column,
        effective_config.reference_column,
        *effective_config.comparative_column_names,
    ]
    subset = subset[list(dict.fromkeys(kept_columns))]
    subset = subset.set_index(config.id_column)

    data_quality = DataQualityReport(
        original_rows=original_rows,
        retained_rows=len(subset),
        dropped_rows=dropped_rows,
        conversion_failures=conversion_failures,
        non_finite_values=non_finite_values,
        dropped_constant_factors=dropped_constant_factors,
        warnings=warnings,
    )
    return subset, effective_config, data_quality


def assert_columns_exist(dataframe: pd.DataFrame, required: list[str]) -> None:
    """Raise ColumnNotFoundError for the first missing configured column."""
    available = list(dataframe.columns)
    for column in required:
        if column not in dataframe.columns:
            raise ColumnNotFoundError(
                column_name=column,
                available_columns=available,
            )


def assert_polarity_completeness(config: GRAConfig) -> None:
    """Verify that every comparative column has a polarity entry."""
    missing = [
        name
        for name in config.comparative_column_names
        if name not in config.comparative_columns
    ]
    if missing:
        raise PolarityConfigError(missing_columns=missing)


def assert_reference_not_constant(
    dataframe: pd.DataFrame,
    reference_column: str,
) -> None:
    """Require the reference sequence to retain discriminatory information."""
    ref_series = dataframe[reference_column]
    ref_min = float(ref_series.min())
    ref_max = float(ref_series.max())
    if np.isclose(ref_max - ref_min, 0.0, atol=EPSILON):
        raise NormalizationError(
            column_name=reference_column,
            constant_value=ref_min,
        )


def drop_constant_comparative_factors(
    dataframe: pd.DataFrame,
    config: GRAConfig,
) -> GRAConfig:
    """Return a config with constant comparative factors removed."""
    retained: dict[str, ColumnConfig] = {}
    dropped: list[str] = []

    for name, column_config in config.comparative_columns.items():
        series = dataframe[name]
        col_min = float(series.min())
        col_max = float(series.max())
        if np.isclose(col_max - col_min, 0.0, atol=EPSILON):
            dropped.append(name)
            continue
        retained[name] = column_config

    if dropped:
        logger.warning(
            "Dropped constant comparative factor(s) with no discriminatory information: %s",
            dropped,
        )

    if not retained:
        raise NormalizationError(
            column_name="all comparative factors",
            constant_value=float("nan"),
        )

    if len(retained) == len(config.comparative_columns):
        return config

    return GRAConfig(
        id_column=config.id_column,
        reference_column=config.reference_column,
        reference_polarity=config.reference_polarity,
        comparative_columns=retained,
        rho=config.rho,
    )


def _small_sample_warnings(retained_rows: int) -> list[str]:
    if retained_rows >= SMALL_SAMPLE_WARNING:
        return []

    warning = (
        f"Only {retained_rows} complete samples remain after cleaning. "
        "GRA can be computed, but the ranking may be unstable; interpret "
        "the result cautiously."
    )
    logger.warning(warning)
    return [warning]


def _log_quality_warnings(
    conversion_failures: dict[str, int],
    non_finite_values: dict[str, int],
) -> None:
    if conversion_failures:
        detail = "; ".join(
            f"{column}: {count} value(s)"
            for column, count in conversion_failures.items()
        )
        logger.warning("Non-numeric values coerced to NaN before GRA: %s", detail)

    if non_finite_values:
        detail = "; ".join(
            f"{column}: {count} value(s)"
            for column, count in non_finite_values.items()
        )
        logger.warning("Infinite values converted to NaN before GRA: %s", detail)
