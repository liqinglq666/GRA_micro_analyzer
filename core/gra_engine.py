# core/gra_engine.py
"""Grey Relational Analysis orchestration facade.

The numerical and data-preparation stages live in focused modules while this
class preserves the public ``GreyRelationalAnalyzer`` API and the historical
``_stage_*`` methods for compatibility.
"""

from __future__ import annotations

import logging

import pandas as pd

from core.data_model import DataQualityReport, GRAConfig, GRAResult, Polarity
from core.data_preparation import (
    assert_columns_exist,
    assert_polarity_completeness,
    assert_reference_not_constant,
    drop_constant_comparative_factors,
    prepare_analysis_data,
)
from core.gra_math import (
    assert_finite_frame,
    assert_finite_series,
    compute_coefficients,
    compute_deltas,
    compute_grades,
    normalise_sequences,
    normalise_series,
    rank_factors,
)

logger = logging.getLogger(__name__)


class GreyRelationalAnalyzer:
    """Stateless facade that executes the complete GRA pipeline."""

    def run(self, dataframe: pd.DataFrame, config: GRAConfig) -> GRAResult:
        """Execute the full GRA pipeline and return a validated result."""
        logger.info(
            "GRA run started — ref='%s', factors=%s, rho=%.2f",
            config.reference_column,
            config.comparative_column_names,
            config.rho,
        )

        clean_df, effective_config, data_quality = self._stage_validate_and_clean(
            dataframe,
            config,
        )
        normalised_df = self._stage_normalise(clean_df, effective_config)
        self._assert_finite_frame(normalised_df, stage="normalisation")

        delta_df = self._stage_compute_deltas(normalised_df, effective_config)
        self._assert_finite_frame(delta_df, stage="absolute_difference")

        coefficient_df = self._stage_compute_coefficients(
            delta_df,
            effective_config.rho,
        )
        self._assert_finite_frame(
            coefficient_df,
            stage="relational_coefficient",
        )

        grg_series = self._stage_compute_grades(coefficient_df)
        self._assert_finite_series(grg_series, stage="grading")
        ranked_factors = self._stage_rank_factors(grg_series)

        result = GRAResult(
            config=effective_config,
            normalised_df=normalised_df,
            delta_df=delta_df,
            coefficient_df=coefficient_df,
            grg_series=grg_series,
            ranked_factors=ranked_factors,
            data_quality=data_quality,
        )
        logger.info("GRA run complete. Top factor: '%s'", result.top_factor)
        return result

    # Compatibility wrappers -------------------------------------------------
    # Keeping these methods avoids breaking scripts/tests that reached into
    # the previous monolithic implementation, while the real work is now
    # delegated to small focused modules.

    def _stage_validate_and_clean(
        self,
        dataframe: pd.DataFrame,
        config: GRAConfig,
    ) -> tuple[pd.DataFrame, GRAConfig, DataQualityReport]:
        return prepare_analysis_data(dataframe, config)

    def _stage_normalise(
        self,
        clean_df: pd.DataFrame,
        config: GRAConfig,
    ) -> pd.DataFrame:
        return normalise_sequences(clean_df, config)

    def _normalise_series(
        self,
        series: pd.Series,
        polarity: Polarity,
        column_name: str,
    ) -> pd.Series:
        return normalise_series(series, polarity, column_name)

    def _stage_compute_deltas(
        self,
        normalised_df: pd.DataFrame,
        config: GRAConfig,
    ) -> pd.DataFrame:
        return compute_deltas(normalised_df, config)

    def _stage_compute_coefficients(
        self,
        delta_df: pd.DataFrame,
        rho: float,
    ) -> pd.DataFrame:
        return compute_coefficients(delta_df, rho)

    def _stage_compute_grades(self, coefficient_df: pd.DataFrame) -> pd.Series:
        return compute_grades(coefficient_df)

    def _stage_rank_factors(self, grg_series: pd.Series) -> list[str]:
        return rank_factors(grg_series)

    def _assert_columns_exist(
        self,
        dataframe: pd.DataFrame,
        required: list[str],
    ) -> None:
        assert_columns_exist(dataframe, required)

    def _assert_polarity_completeness(self, config: GRAConfig) -> None:
        assert_polarity_completeness(config)

    def _assert_reference_not_constant(
        self,
        dataframe: pd.DataFrame,
        reference_column: str,
    ) -> None:
        assert_reference_not_constant(dataframe, reference_column)

    def _drop_constant_comparative_factors(
        self,
        dataframe: pd.DataFrame,
        config: GRAConfig,
    ) -> GRAConfig:
        return drop_constant_comparative_factors(dataframe, config)

    def _assert_finite_frame(self, dataframe: pd.DataFrame, stage: str) -> None:
        assert_finite_frame(dataframe, stage)

    def _assert_finite_series(self, series: pd.Series, stage: str) -> None:
        assert_finite_series(series, stage)
