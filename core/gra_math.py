"""Pure numerical stages used by the Grey Relational Analysis pipeline."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from core.constants import EPSILON
from core.data_model import GRAConfig, Polarity
from core.exceptions import ComputationError, NormalizationError

logger = logging.getLogger(__name__)


def normalise_sequences(clean_df: pd.DataFrame, config: GRAConfig) -> pd.DataFrame:
    """Apply polarity-aware min-max normalisation to reference and factors."""
    normalised_parts = [
        normalise_series(
            clean_df[config.reference_column],
            config.reference_polarity,
            config.reference_column,
        )
    ]
    normalised_parts.extend(
        normalise_series(clean_df[name], column_config.polarity, name)
        for name, column_config in config.comparative_columns.items()
    )

    normalised_df = pd.concat(normalised_parts, axis=1)
    logger.debug(
        "Normalisation complete — shape %s, range [%.4f, %.4f].",
        normalised_df.shape,
        float(normalised_df.min().min()),
        float(normalised_df.max().max()),
    )
    return normalised_df


def normalise_series(
    series: pd.Series,
    polarity: Polarity,
    column_name: str,
) -> pd.Series:
    """Normalise one finite sequence using its configured polarity."""
    values = series.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise NormalizationError(
            column_name=column_name,
            constant_value=float("nan"),
        )

    col_min = float(series.min())
    col_max = float(series.max())
    col_range = col_max - col_min

    if np.isclose(col_range, 0.0, atol=EPSILON):
        raise NormalizationError(
            column_name=column_name,
            constant_value=col_min,
        )

    if polarity == Polarity.LTB:
        normalised = (series - col_min) / col_range
    else:
        normalised = (col_max - series) / col_range
    return normalised.rename(column_name)


def compute_deltas(normalised_df: pd.DataFrame, config: GRAConfig) -> pd.DataFrame:
    """Compute the absolute-difference matrix |x0*(k) - xi*(k)|."""
    try:
        ref_normalised = normalised_df[config.reference_column]
        comp_normalised = normalised_df[config.comparative_column_names]
        delta_df = comp_normalised.sub(ref_normalised, axis=0).abs()
    except Exception as exc:
        raise ComputationError(
            stage="absolute_difference",
            detail=str(exc),
        ) from exc

    logger.debug(
        "Delta matrix — Δ_min=%.4f, Δ_max=%.4f.",
        float(delta_df.min().min()),
        float(delta_df.max().max()),
    )
    return delta_df


def compute_coefficients(delta_df: pd.DataFrame, rho: float) -> pd.DataFrame:
    """Compute Deng grey relational coefficients from the delta matrix."""
    try:
        delta_min = float(delta_df.min().min())
        delta_max = float(delta_df.max().max())

        if not np.isfinite(delta_min) or not np.isfinite(delta_max):
            raise ValueError("Delta extrema are not finite.")

        if np.isclose(delta_max, 0.0, atol=EPSILON):
            logger.warning(
                "Global Δ_max ≈ 0; all retained sequences are identical to "
                "the reference. Coefficients set to 1.0."
            )
            return pd.DataFrame(
                np.ones_like(delta_df.values, dtype=float),
                index=delta_df.index,
                columns=delta_df.columns,
            )

        numerator = delta_min + rho * delta_max
        denominator = delta_df + rho * delta_max
        coefficient_df = numerator / denominator
    except Exception as exc:
        raise ComputationError(
            stage="relational_coefficient",
            detail=str(exc),
        ) from exc

    logger.debug(
        "Coefficient matrix — ξ_min=%.4f, ξ_max=%.4f.",
        float(coefficient_df.min().min()),
        float(coefficient_df.max().max()),
    )
    return coefficient_df


def compute_grades(coefficient_df: pd.DataFrame) -> pd.Series:
    """Compute one GRG per comparative factor without skipping NaN values."""
    try:
        grg_series = coefficient_df.mean(axis=0, skipna=False)
    except Exception as exc:
        raise ComputationError(
            stage="grading",
            detail=str(exc),
        ) from exc

    logger.debug(
        "GRG computed — min=%.4f, max=%.4f.",
        float(grg_series.min()),
        float(grg_series.max()),
    )
    return grg_series


def rank_factors(grg_series: pd.Series) -> list[str]:
    """Return factors sorted by descending GRG using stable ordering."""
    ranked = grg_series.sort_values(ascending=False, kind="mergesort")
    return list(ranked.index)


def assert_finite_frame(dataframe: pd.DataFrame, stage: str) -> None:
    """Reject NaN/+Inf/-Inf produced within a computation stage."""
    try:
        values = dataframe.to_numpy(dtype=float)
        is_finite = np.isfinite(values)
    except Exception as exc:
        raise ComputationError(stage=stage, detail=str(exc)) from exc

    if not is_finite.all():
        bad_count = int((~is_finite).sum())
        raise ComputationError(
            stage=stage,
            detail=(
                f"{bad_count} non-finite value(s) were produced. "
                "Computation stopped to avoid silently biased GRG values."
            ),
        )


def assert_finite_series(series: pd.Series, stage: str) -> None:
    """Reject non-finite values in a computed result series."""
    values = series.to_numpy(dtype=float)
    is_finite = np.isfinite(values)
    if not is_finite.all():
        bad_count = int((~is_finite).sum())
        raise ComputationError(
            stage=stage,
            detail=(
                f"{bad_count} non-finite result value(s) were produced. "
                "Computation stopped rather than returning partial GRG values."
            ),
        )
