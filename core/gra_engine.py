# core/gra_engine.py
"""
GRA-MicroAnalyzer 鈥� Grey Relational Analysis Engine
====================================================
Implements the complete Deng (1989) Grey Relational Analysis pipeline
using fully vectorised Pandas / NumPy operations.

Mathematical Pipeline
---------------------
Given n samples and m comparative factors:

1. Normalisation (polarity-aware):
   - LTB: x*(k) = (x(k) - min_k) / (max_k - min_k)
   - STB: x*(k) = (max_k - x(k)) / (max_k - min_k)

2. Absolute Difference:
   螖_i(k) = |x*_0(k) - x*_i(k)|
   where x*_0 is the normalised reference sequence.

3. Global extremes:
   螖_min = min over all i, k of 螖_i(k)
   螖_max = max over all i, k of 螖_i(k)

4. Grey Relational Coefficient:
   尉_i(k) = (螖_min + 蟻路螖_max) / (螖_i(k) + 蟻路螖_max)

5. Grey Relational Grade (GRG):
   纬_i = (1/n) 危_k 尉_i(k)

Engineering Constraints
-----------------------
- Zero iteration over DataFrame rows.  All operations use broadcasting.
- The engine is stateless; instantiate once and call `run()` as many
  times as needed with different DataFrames or configs.
- The engine never mutates its inputs.
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
_EPSILON: Final[float] = 1e-12  # Guard against floating-point underflow


class GreyRelationalAnalyzer:
    """
    Stateless GRA computation engine.

    Instantiate once; call :py:meth:`run` for each analysis.

    Parameters
    ----------
    None 鈥� all parameters are supplied per-run via :py:meth:`run`.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, dataframe: pd.DataFrame, config: GRAConfig) -> GRAResult:
        """
        Execute the full GRA pipeline and return a validated result.

        Parameters
        ----------
        dataframe:
            The raw data loaded from the user's file.  Must contain at
            least the reference column and all comparative columns.
        config:
            Fully validated :class:`GRAConfig` produced by the UI layer.

        Returns
        -------
        GRAResult
            Immutable result container with all intermediate artefacts.

        Raises
        ------
        InsufficientDataError
            When *dataframe* contains fewer than 2 rows after dropping NaNs.
        ColumnNotFoundError
            When any configured column is absent from *dataframe*.
        PolarityConfigError
            When a comparative column has no polarity entry in *config*.
        NormalizationError
            When a column is constant (zero range), making normalisation
            undefined.
        ComputationError
            For any unexpected numerical failure in the pipeline.
        """
        logger.info(
            "GRA run started 鈥� ref='%s', factors=%s, rho=%.2f",
            config.reference_column,
            config.comparative_column_names,
            config.rho,
        )

        clean_df = self._stage_validate_and_clean(dataframe, config)
        normalised_df = self._stage_normalise(clean_df, config)
        delta_df = self._stage_compute_deltas(normalised_df, config)
        coefficient_df = self._stage_compute_coefficients(delta_df, config.rho)
        grg_series = self._stage_compute_grades(coefficient_df)
        ranked_factors = self._stage_rank_factors(grg_series)

        result = GRAResult(
            config=config,
            normalised_df=normalised_df,
            delta_df=delta_df,
            coefficient_df=coefficient_df,
            grg_series=grg_series,
            ranked_factors=ranked_factors,
        )
        logger.info("GRA run complete. Top factor: '%s'", result.top_factor)
        return result

    # ------------------------------------------------------------------
    # Stage 1 鈥� Validation & Cleaning
    # ------------------------------------------------------------------

    def _stage_validate_and_clean(
        self, dataframe: pd.DataFrame, config: GRAConfig
    ) -> pd.DataFrame:
        """
        Validate column presence, drop NaN rows, and enforce the minimum
        sample count.

        Parameters
        ----------
        dataframe:
            Raw input DataFrame.
        config:
            Analysis configuration.

        Returns
        -------
        pd.DataFrame
            Subset containing only the columns required for computation,
            with NaN rows removed and the ID column set as the index.
        """
        required_columns: list[str] = [
            config.reference_column,
            *config.comparative_column_names,
        ]

        self._assert_columns_exist(dataframe, required_columns)
        self._assert_polarity_completeness(config)

        all_columns = [config.id_column] + required_columns
        # Deduplicate while preserving order (id_column may equal ref or comp)
        seen: set[str] = set()
        unique_columns: list[str] = []
        for col in all_columns:
            if col not in seen:
                unique_columns.append(col)
                seen.add(col)

        subset = dataframe[unique_columns].copy()
        numeric_columns = [config.reference_column] + config.comparative_column_names
        subset_before = len(subset)
        subset = subset.dropna(subset=numeric_columns)
        dropped = subset_before - len(subset)
        if dropped > 0:
            logger.warning(
                "%d row(s) dropped due to missing values in numeric columns.",
                dropped,
            )

        if len(subset) < _MINIMUM_SAMPLES:
            raise InsufficientDataError(
                row_count=len(subset),
                minimum_required=_MINIMUM_SAMPLES,
            )

        if config.id_column in subset.columns:
            subset = subset.set_index(config.id_column)

        return subset

    # ------------------------------------------------------------------
    # Stage 2 鈥� Polarity-Aware Normalisation
    # ------------------------------------------------------------------

    def _stage_normalise(
        self, clean_df: pd.DataFrame, config: GRAConfig
    ) -> pd.DataFrame:
        """
        Apply LTB or STB normalisation to every sequence (reference + all
        comparative columns) using fully vectorised operations.

        Parameters
        ----------
        clean_df:
            Cleaned DataFrame with ID column as index.
        config:
            Analysis configuration carrying polarity assignments.

        Returns
        -------
        pd.DataFrame
            DataFrame of the same shape as *clean_df* with values in [0, 1].
        """
        normalised_parts: list[pd.Series] = []

        # Normalise the reference sequence
        ref_series = self._normalise_series(
            series=clean_df[config.reference_column],
            polarity=config.reference_polarity,
            column_name=config.reference_column,
        )
        normalised_parts.append(ref_series)

        # Normalise each comparative sequence
        for col_name, col_cfg in config.comparative_columns.items():
            norm_series = self._normalise_series(
                series=clean_df[col_name],
                polarity=col_cfg.polarity,
                column_name=col_name,
            )
            normalised_parts.append(norm_series)

        normalised_df = pd.concat(normalised_parts, axis=1)
        logger.debug(
            "Normalisation complete 鈥� shape %s, range [%.4f, %.4f].",
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
        """
        Normalise a single Series according to its polarity.

        Parameters
        ----------
        series:
            Raw numeric data for one column.
        polarity:
            :attr:`Polarity.LTB` or :attr:`Polarity.STB`.
        column_name:
            Used in error messages if normalisation fails.

        Returns
        -------
        pd.Series
            Normalised values in [0, 1] with the original name preserved.

        Raises
        ------
        NormalizationError
            If all values in *series* are identical (zero range).
        """
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
        else:  # Polarity.STB
            normalised = (col_max - series) / col_range

        return normalised.rename(column_name)

    # ------------------------------------------------------------------
    # Stage 3 鈥� Absolute Difference Matrix
    # ------------------------------------------------------------------

    def _stage_compute_deltas(
        self, normalised_df: pd.DataFrame, config: GRAConfig
    ) -> pd.DataFrame:
        """
        Compute the element-wise absolute difference between the normalised
        reference sequence and each normalised comparative sequence.

        螖_i(k) = |x*_0(k) - x*_i(k)|

        Uses DataFrame broadcasting 鈥� no row iteration.

        Parameters
        ----------
        normalised_df:
            Output from :py:meth:`_stage_normalise`.
        config:
            Provides the reference column name.

        Returns
        -------
        pd.DataFrame
            Shape (n_samples, n_comparative) containing |螖| values.
        """
        try:
            ref_normalised: pd.Series = normalised_df[config.reference_column]
            comp_normalised: pd.DataFrame = normalised_df[
                config.comparative_column_names
            ]
            # Broadcasting: ref_normalised is aligned on the index axis
            delta_df: pd.DataFrame = comp_normalised.sub(ref_normalised, axis=0).abs()
        except Exception as exc:
            raise ComputationError(
                stage="absolute_difference",
                detail=str(exc),
            ) from exc

        logger.debug(
            "Delta matrix 鈥� 螖_min=%.4f, 螖_max=%.4f.",
            float(delta_df.min().min()),
            float(delta_df.max().max()),
        )
        return delta_df

    # ------------------------------------------------------------------
    # Stage 4 鈥� Grey Relational Coefficients
    # ------------------------------------------------------------------

    def _stage_compute_coefficients(
        self, delta_df: pd.DataFrame, rho: float
    ) -> pd.DataFrame:
        """
        Compute the Grey Relational Coefficient matrix.

        尉_i(k) = (螖_min + 蟻路螖_max) / (螖_i(k) + 蟻路螖_max)

        螖_min and 螖_max are the **global** minimum and maximum across all
        samples and all comparative factors, consistent with Deng (1989).

        Parameters
        ----------
        delta_df:
            Absolute difference matrix from :py:meth:`_stage_compute_deltas`.
        rho:
            Distinguishing coefficient 蟻.

        Returns
        -------
        pd.DataFrame
            Shape identical to *delta_df*, values in (0, 1].
        """
        try:
            delta_min: float = float(delta_df.min().min())
            delta_max: float = float(delta_df.max().max())

            # Denominator guard: if delta_max 鈮� 0, all sequences are identical
            # to the reference 鈥� coefficients are trivially 1.
            if np.isclose(delta_max, 0.0, atol=_EPSILON):
                logger.warning(
                    "Global 螖_max 鈮� 0; all sequences are identical to "
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
            "Coefficient matrix 鈥� 尉_min=%.4f, 尉_max=%.4f.",
            float(coefficient_df.min().min()),
            float(coefficient_df.max().max()),
        )
        return coefficient_df

    # ------------------------------------------------------------------
    # Stage 5 鈥� Grey Relational Grade
    # ------------------------------------------------------------------

    def _stage_compute_grades(
        self, coefficient_df: pd.DataFrame
    ) -> pd.Series:
        """
        Compute the Grey Relational Grade (GRG) for each comparative factor
        by averaging the relational coefficients across all samples.

        纬_i = (1/n) 危_k 尉_i(k)

        Parameters
        ----------
        coefficient_df:
            Relational coefficient matrix.

        Returns
        -------
        pd.Series
            GRG value indexed by comparative column name, unsorted.
        """
        try:
            grg_series: pd.Series = coefficient_df.mean(axis=0)
        except Exception as exc:
            raise ComputationError(
                stage="grading",
                detail=str(exc),
            ) from exc

        logger.debug(
            "GRG computed 鈥� min=%.4f, max=%.4f.",
            float(grg_series.min()),
            float(grg_series.max()),
        )
        return grg_series

    # ------------------------------------------------------------------
    # Stage 6 鈥� Ranking
    # ------------------------------------------------------------------

    def _stage_rank_factors(self, grg_series: pd.Series) -> list[str]:
        """
        Sort comparative factors by GRG in descending order.

        Parameters
        ----------
        grg_series:
            Unsorted GRG values from :py:meth:`_stage_compute_grades`.

        Returns
        -------
        list[str]
            Column names sorted from most to least influential.
        """
        ranked: pd.Series = grg_series.sort_values(ascending=False)
        return list(ranked.index)

    # ------------------------------------------------------------------
    # Validation Helpers
    # ------------------------------------------------------------------

    def _assert_columns_exist(
        self, dataframe: pd.DataFrame, required: list[str]
    ) -> None:
        """
        Raise :class:`ColumnNotFoundError` for the first missing column.

        Parameters
        ----------
        dataframe:
            The DataFrame to check.
        required:
            Column names that must be present.
        """
        available: list[str] = list(dataframe.columns)
        for col in required:
            if col not in dataframe.columns:
                raise ColumnNotFoundError(
                    column_name=col,
                    available_columns=available,
                )

    def _assert_polarity_completeness(self, config: GRAConfig) -> None:
        """
        Verify that every comparative column has a polarity entry.

        Parameters
        ----------
        config:
            The analysis configuration to inspect.

        Raises
        ------
        PolarityConfigError
            If any comparative column lacks a polarity assignment.
        """
        missing: list[str] = [
            name
            for name in config.comparative_column_names
            if name not in config.comparative_columns
        ]
        if missing:
            raise PolarityConfigError(missing_columns=missing)
