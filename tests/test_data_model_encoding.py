from __future__ import annotations

import pandas as pd

from core.data_model import ColumnConfig, GRAConfig, GRAResult, Polarity


def test_summary_uses_readable_symbols():
    config = GRAConfig(
        id_column="sample",
        reference_column="strength",
        reference_polarity=Polarity.LTB,
        comparative_columns={
            "porosity": ColumnConfig(name="porosity", polarity=Polarity.STB),
        },
        rho=0.5,
    )
    result = GRAResult(
        config=config,
        normalised_df=pd.DataFrame({"strength": [0.0, 1.0], "porosity": [1.0, 0.0]}),
        delta_df=pd.DataFrame({"porosity": [1.0, 1.0]}),
        coefficient_df=pd.DataFrame({"porosity": [0.5, 0.5]}),
        grg_series=pd.Series({"porosity": 0.5}),
        ranked_factors=["porosity"],
    )

    summary = result.summary_string()

    assert "ρ = 0.5" in summary
    assert "鈥" not in summary
    assert "蟻" not in summary
