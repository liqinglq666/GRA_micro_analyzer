import math

import numpy as np
import pandas as pd
import pytest

from core.data_model import ColumnConfig, GRAConfig, Polarity
from core.exceptions import ColumnNotFoundError, NormalizationError
from core.gra_engine import GreyRelationalAnalyzer


def _config(comparative_columns, rho=0.5):
    return GRAConfig(
        id_column="Sample",
        reference_column="Target",
        reference_polarity=Polarity.LTB,
        comparative_columns={
            name: ColumnConfig(name=name, polarity=polarity)
            for name, polarity in comparative_columns.items()
        },
        rho=rho,
    )


def test_gra_engine_basic_ranking():
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C"],
            "Target": [1.0, 2.0, 3.0],
            "Factor_A": [1.0, 2.0, 3.0],
            "Factor_B": [3.0, 2.0, 1.0],
        }
    )
    result = GreyRelationalAnalyzer().run(
        df,
        _config({"Factor_A": Polarity.LTB, "Factor_B": Polarity.LTB}),
    )
    assert result.top_factor == "Factor_A"
    assert math.isclose(result.grg_series["Factor_A"], 1.0)
    assert result.n_samples == 3
    assert result.n_factors == 2


def test_exact_coefficients_match_manual_calculation():
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C"],
            "Target": [1.0, 2.0, 3.0],
            "Factor_A": [1.0, 2.0, 3.0],
            "Factor_B": [1.0, 1.5, 3.0],
        }
    )
    result = GreyRelationalAnalyzer().run(
        df,
        _config({"Factor_A": Polarity.LTB, "Factor_B": Polarity.LTB}),
    )

    expected_b = np.array([1.0, 1.0 / 3.0, 1.0])
    assert np.allclose(result.coefficient_df["Factor_B"].to_numpy(), expected_b)
    assert math.isclose(
        result.grg_series["Factor_B"], expected_b.mean(), rel_tol=1e-12
    )


def test_stb_normalisation_can_match_ltb_reference_trend():
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C"],
            "Target": [1.0, 2.0, 3.0],
            "SmallerFactor": [3.0, 2.0, 1.0],
        }
    )
    result = GreyRelationalAnalyzer().run(
        df,
        _config({"SmallerFactor": Polarity.STB}),
    )

    assert np.allclose(
        result.normalised_df["Target"],
        result.normalised_df["SmallerFactor"],
    )
    assert math.isclose(result.grg_series["SmallerFactor"], 1.0)


def test_non_numeric_values_are_dropped_before_analysis():
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C", "D"],
            "Target": ["1", "bad", "3", "4"],
            "Factor_A": [1, 2, 3, 4],
            "Factor_B": [4, 3, 2, 1],
        }
    )
    result = GreyRelationalAnalyzer().run(
        df,
        _config({"Factor_A": Polarity.LTB, "Factor_B": Polarity.STB}),
    )
    assert result.n_samples == 3
    assert "B" not in result.normalised_df.index
    assert result.data_quality.original_rows == 4
    assert result.data_quality.retained_rows == 3
    assert result.data_quality.dropped_rows == 1
    assert result.data_quality.conversion_failures == {"Target": 1}


def test_infinite_values_are_removed_and_reported():
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C", "D"],
            "Target": [1.0, 2.0, 3.0, 4.0],
            "Factor_A": [1.0, np.inf, 3.0, 4.0],
            "Factor_B": [4.0, 3.0, 2.0, 1.0],
        }
    )
    result = GreyRelationalAnalyzer().run(
        df,
        _config({"Factor_A": Polarity.LTB, "Factor_B": Polarity.STB}),
    )

    assert result.n_samples == 3
    assert "B" not in result.normalised_df.index
    assert result.data_quality.non_finite_values == {"Factor_A": 1}
    assert np.isfinite(result.coefficient_df.to_numpy()).all()
    assert np.isfinite(result.grg_series.to_numpy()).all()


def test_constant_comparative_factor_is_dropped_and_reported():
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C"],
            "Target": [1, 2, 3],
            "Constant": [5, 5, 5],
            "Varying": [1, 2, 4],
        }
    )
    result = GreyRelationalAnalyzer().run(
        df,
        _config({"Constant": Polarity.LTB, "Varying": Polarity.LTB}),
    )
    assert "Constant" not in result.ranked_factors
    assert result.ranked_factors == ["Varying"]
    assert result.data_quality.dropped_constant_factors == ["Constant"]


def test_constant_reference_raises_normalization_error():
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C"],
            "Target": [1, 1, 1],
            "Factor_A": [1, 2, 3],
        }
    )
    with pytest.raises(NormalizationError):
        GreyRelationalAnalyzer().run(df, _config({"Factor_A": Polarity.LTB}))


def test_identical_reference_and_factor_produce_unit_coefficients():
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C"],
            "Target": [1.0, 2.0, 3.0],
            "Factor_A": [1.0, 2.0, 3.0],
        }
    )
    result = GreyRelationalAnalyzer().run(
        df,
        _config({"Factor_A": Polarity.LTB}),
    )
    assert np.allclose(result.coefficient_df["Factor_A"], 1.0)
    assert math.isclose(result.grg_series["Factor_A"], 1.0)


@pytest.mark.parametrize("rho", [0.01, 0.5, 1.0])
def test_supported_rho_range_produces_finite_results(rho):
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C", "D"],
            "Target": [1.0, 2.0, 3.0, 4.0],
            "Factor_A": [1.0, 1.5, 2.5, 4.0],
        }
    )
    result = GreyRelationalAnalyzer().run(
        df,
        _config({"Factor_A": Polarity.LTB}, rho=rho),
    )
    assert np.isfinite(result.grg_series.to_numpy()).all()
    assert ((result.coefficient_df >= 0.0) & (result.coefficient_df <= 1.0)).all().all()


def test_missing_id_column_raises_domain_error():
    df = pd.DataFrame(
        {
            "Target": [1.0, 2.0, 3.0],
            "Factor_A": [1.0, 2.0, 3.0],
        }
    )
    with pytest.raises(ColumnNotFoundError):
        GreyRelationalAnalyzer().run(df, _config({"Factor_A": Polarity.LTB}))


def test_tied_grades_receive_same_rank():
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C"],
            "Target": [1.0, 2.0, 3.0],
            "Factor_A": [1.0, 2.0, 3.0],
            "Factor_B": [10.0, 20.0, 30.0],
            "Factor_C": [1.0, 1.5, 3.0],
        }
    )
    result = GreyRelationalAnalyzer().run(
        df,
        _config(
            {
                "Factor_A": Polarity.LTB,
                "Factor_B": Polarity.LTB,
                "Factor_C": Polarity.LTB,
            }
        ),
    )

    assert result.rank_by_factor["Factor_A"] == 1
    assert result.rank_by_factor["Factor_B"] == 1
    assert result.rank_by_factor["Factor_C"] == 3
