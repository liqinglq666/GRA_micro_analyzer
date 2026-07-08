import math

import pandas as pd
import pytest

from core.data_model import ColumnConfig, GRAConfig, Polarity
from core.exceptions import NormalizationError
from core.gra_engine import GreyRelationalAnalyzer


def _config(comparative_columns):
    return GRAConfig(
        id_column="Sample",
        reference_column="Target",
        reference_polarity=Polarity.LTB,
        comparative_columns={
            name: ColumnConfig(name=name, polarity=polarity)
            for name, polarity in comparative_columns.items()
        },
        rho=0.5,
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


def test_constant_comparative_factor_is_dropped():
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
