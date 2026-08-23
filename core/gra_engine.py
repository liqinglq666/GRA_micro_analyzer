# core/gra_engine.py
"""
GRA-MicroAnalyzer — Grey Relational Analysis Engine
====================================================
Implements the complete Deng (1989) Grey Relational Analysis pipeline
using vectorised Pandas / NumPy operations.
"""

from __future__ import annotations

import logging
from typing import Final

import numpy as np
import pandas as pd

from core.data_model import GRAConfig, GRAResult, Polarity
from core.exceptions import (
    ColumnNotFoundError,
    ComputationError,
    InsufficientDataError,
    NormalizationError,
    PolarityConfigError,
)

logger = logging.getLogger(__name__)

_MINIMUM_SAMPLES: Final[int] = 2
_EPSILON: Final[float] = 1e-12


class GreyRelationalAnalyzer:
    """Stateless GRA computation engine."""

    def run(self, dataframe: pd.DataFrame, config: GRAConfig) -> GRAResult:
        """Execute the full GRA pipeline and return a validated result."""
        logger.info(
            "GRA run started — ref='%s', factors=%s, rho=%.2f",
            config.reference_column,
            config.comparative_column_names,
            config.rho,
        )

        clean_df, effective_config = self._stage_validate_and_clean(dataframe, config)
        normalised_df = self._stage_normalise(clean_df, effective_config)
        delta_df = self._stage_compute_deltas(normalised_df, effective_config)
        coefficient_df = self._stage_compute_coefficients(delta_df, effective_config.rho)
        grg_series = self._stage_compute_grades(coefficient_df)
        ranked_factors = self._stage_rank_factors(grg_series)

        result = GRAResult(
            config=effective_config,
            normalised_df=normalised_df,
            delta_df=delta_df,
            coefficient_df=coefficient_df,
            grg_series=grg_series,
            ranked_factors=ranked_factors,
        )
        logger.info("GRA run complete. Top factor: '%s'", result.top_factor)
        return result

    # ------------------------------------------------------------------
    # Stage 1 — Validation & Cleaning
    # ------------------------------------------------------------------

    def _stage_validate_and_clean(
        self, dataframe: pd.DataFrame, config: GRAConfig
    ) -> tuple[pd.DataFrame, GRAConfig]:
        """
        Validate columns, coerce numerical data, drop invalid rows, remove
        constant comparative factors, and enforce the minimum sample count.
        """
        required_columns: list[str] = [
            config.reference_column,
            *config.comparative_column_names,
        ]

        self._assert_columns_exist(dataframe, required_columns)
        self._assert_polarity_completeness(config)

        all_columns = [config.id_column] + required_columns
        unique_columns = list(dict.fromkeys(all_columns))
        subset = dataframe[unique_columns].copy()
        numeric_columns = [config.reference_column] + config.comparative_column_names

        conversion_failures: dict[str, int] = {}
        for col in numeric_columns:
            original_non_empty = subset[col].notna() & (subset[col].astype(str).str.strip() != "")
            coerced = pd.to_numeric(subset[col], errors="coerce")
            failed = int((original_non_empty & coerced.isna()).sum())
            if failed:
                conversion_failures[col] = failed
            subset[col] = coerced

        if conversion_failures:
            detail = "; ".join(
                f"{col}: {count} value(s)" for col, count in conversion_failures.items()
            )
            logger.warning("Non-numeric values coerced to NaN before GRA: %s", detail)

        subset_before = len(subset)
        subset = subset.dropna(subset=numeric_columns)
        dropped = subset_before - len(subset)
        if dropped > 0:
            logger.warning(
                "%d row(s) dropped due to missing or non-numeric values in analysis columns.",
                dropped,
            )

        if len(subset) < _MINIMUM_SAMPLES:
            raise InsufficientDataError(
                row_count=len(subset),
                minimum_required=_MINIMUM_SAMPLES,
            )

        self._assert_reference_not_constant(subset, config.reference_column)
        effective_config = self._drop_constant_comparative_factors(subset, config)

        kept_columns = [config.id_column, effective_config.reference_column, *effective_config.comparative_column_names]
        kept_columns = list(dict.fromkeys([c for c in kept_columns if c in subset.columns]))
        subset = subset[kept_columns]

        if config.id_column in subset.columns:
            subset = subset.set_index(config.id_column)

        return subset, effective_config

    # ------------------------------------------------------------------
    # Stage 2 — Polarity-Aware Normalisation
    # ------------------------------------------------------------------

    def _stage_normalise(
        self, clean_df: pd.DataFrame, config: GRAConfig
    ) -> pd.DataFrame:
        """Apply LTB/STB normalisation to the reference and factor columns."""
        normalised_parts: list[pd.Series] = []

        ref_series = self._normalise_series(
            series=clean_df[config.reference_column],
            polarity=config.reference_polarity,
            column_name=config.reference_column,
        )
        normalised_parts.append(ref_series)

        for col_name, col_cfg in config.comparative_columns.items():
            norm_series = self._normalise_series(
                series=clean_df[col_name],
                polarity=col_cfg.polarity,
                column_name=col_name,
            )
            normalised_parts.append(norm_series)

        normalised_df = pd.concat(normalised_parts, axis=1)
        logger.debug(
            "Normalisation complete — shape %s, range [%.4f, %.4f].",
            normalised_df.shape,
            float(normalised_df.min().min()),
            float(normalised_df.max().max()),
        )
        return normalised_df

    def _normalise_series(
        self,
        series: pd.Series,
        polarity: Polarity,
        column_name: str,
    ) -> pd.Series:
        """Normalise a single Series according to its polarity."""
        col_min: float = float(series.min())
        col_max: float = float(series.max())
        col_range: float = col_max - col_min

        if np.isclose(col_range, 0.0, atol=_EPSILON):
            raise NormalizationError(
                column_name=column_name,
                constant_value=col_min,
            )

        if polarity == Polarity.LTB:
            normalised = (series - col_min) / col_range
        else:
            normalised = (col_max - series) / col_range

        return normalised.rename(column_name)

    # ------------------------------------------------------------------
    # Stage 3 — Absolute Difference Matrix
    # ------------------------------------------------------------------

    def _stage_compute_deltas(
        self, normalised_df: pd.DataFrame, config: GRAConfig
    ) -> pd.DataFrame:
        """Compute |x0*(k) - xi*(k)| for each comparative sequence."""
        try:
            ref_normalised: pd.Series = normalised_df[config.reference_column]
            comp_normalised: pd.DataFrame = normalised_df[
                config.comparative_column_names
            ]
            delta_df: pd.DataFrame = comp_normalised.sub(ref_normalised, axis=0).abs()
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

    # ------------------------------------------------------------------
    # Stage 4 — Grey Relational Coefficients
    # ------------------------------------------------------------------

    def _stage_compute_coefficients(
        self, delta_df: pd.DataFrame, rho: float
    ) -> pd.DataFrame:
        """Compute the Grey Relational Coefficient matrix."""
        try:
            delta_min: float = float(delta_df.min().min())
            delta_max: float = float(delta_df.max().max())

            if np.isclose(delta_max, 0.0, atol=_EPSILON):
                logger.warning(
                    "Global Δ_max ≈ 0; all retained sequences are identical to "
                    "the reference. Coefficients set to 1.0."
                )
                return pd.DataFrame(
                    np.ones_like(delta_df.values),
                    index=delta_df.index,
                    columns=delta_df.columns,
                )

            numerator: float = delta_min + rho * delta_max
            denominator: pd.DataFrame = delta_df + rho * delta_max
            coefficient_df: pd.DataFrame = numerator / denominator
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

    # ------------------------------------------------------------------
    # Stage 5 — Grey Relational Grades
    # ------------------------------------------------------------------

    def _stage_compute_grades(
        self, coefficient_df: pd.DataFrame
    ) -> pd.Series:
        """Compute GRG for each comparative factor."""
        try:
            grg_series: pd.Series = coefficient_df.mean(axis=0)
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

    # ------------------------------------------------------------------
    # Stage 6 — Ranking
    # ------------------------------------------------------------------

    def _stage_rank_factors(self, grg_series: pd.Series) -> list[str]:
        """Sort comparative factors by GRG in descending order."""
        ranked: pd.Series = grg_series.sort_values(ascending=False)
        return list(ranked.index)

    # ------------------------------------------------------------------
    # Validation Helpers
    # ------------------------------------------------------------------

    def _assert_columns_exist(
        self, dataframe: pd.DataFrame, required: list[str]
    ) -> None:
        """Raise ColumnNotFoundError for the first missing column."""
        available: list[str] = list(dataframe.columns)
        for col in required:
            if col not in dataframe.columns:
                raise ColumnNotFoundError(
                    column_name=col,
                    available_columns=available,
                )

    def _assert_polarity_completeness(self, config: GRAConfig) -> None:
        """Verify that every comparative column has a polarity entry."""
        missing: list[str] = [
            name
            for name in config.comparative_column_names
            if name not in config.comparative_columns
        ]
        if missing:
            raise PolarityConfigError(missing_columns=missing)

    def _assert_reference_not_constant(self, dataframe: pd.DataFrame, reference_column: str) -> None:
        """Reference sequence must contain discriminatory information."""
        ref_series = dataframe[reference_column]
        ref_min = float(ref_series.min())
        ref_max = float(ref_series.max())
        if np.isclose(ref_max - ref_min, 0.0, atol=_EPSILON):
            raise NormalizationError(
                column_name=reference_column,
                constant_value=ref_min,
            )

    def _drop_constant_comparative_factors(
        self, dataframe: pd.DataFrame, config: GRAConfig
    ) -> GRAConfig:
        """Drop constant comparative factors instead of failing the whole run."""
        retained = {}
        dropped: list[str] = []

        for name, cfg in config.comparative_columns.items():
            series = dataframe[name]
            col_min = float(series.min())
            col_max = float(series.max())
            if np.isclose(col_max - col_min, 0.0, atol=_EPSILON):
                dropped.append(name)
                continue
            retained[name] = cfg

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
