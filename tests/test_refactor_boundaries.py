import math

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.data_model import ColumnConfig, GRAConfig, Polarity
from core.data_preparation import prepare_analysis_data
from core.gra_engine import GreyRelationalAnalyzer
from core.gra_math import (
    compute_coefficients,
    compute_deltas,
    compute_grades,
    normalise_sequences,
    rank_factors,
)
from ui.result_helpers import limited_network_scores, radar_payload
from ui.table_model import PandasTableModel, model_to_tsv, selected_indexes_to_tsv
from ui.widgets.radar_widget import RadarWidget
from utils.data_inspection import detect_reliable_numeric_columns


def _config() -> GRAConfig:
    return GRAConfig(
        id_column="Sample",
        reference_column="Target",
        reference_polarity=Polarity.LTB,
        comparative_columns={
            "Factor_A": ColumnConfig(name="Factor_A", polarity=Polarity.LTB),
            "Factor_B": ColumnConfig(name="Factor_B", polarity=Polarity.STB),
        },
        rho=0.5,
    )


def _dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Sample": ["A", "B", "C", "D"],
            "Target": [1.0, 2.0, 3.0, 4.0],
            "Factor_A": [1.0, 1.5, 3.0, 4.0],
            "Factor_B": [4.0, 3.0, 2.0, 1.0],
        }
    )


def test_engine_compatibility_wrappers_match_extracted_stages():
    dataframe = _dataframe()
    config = _config()
    analyzer = GreyRelationalAnalyzer()

    clean_a, config_a, quality_a = analyzer._stage_validate_and_clean(dataframe, config)
    clean_b, config_b, quality_b = prepare_analysis_data(dataframe, config)
    pd.testing.assert_frame_equal(clean_a, clean_b)
    assert config_a == config_b
    assert quality_a == quality_b

    normalised_a = analyzer._stage_normalise(clean_a, config_a)
    normalised_b = normalise_sequences(clean_b, config_b)
    pd.testing.assert_frame_equal(normalised_a, normalised_b)

    delta_a = analyzer._stage_compute_deltas(normalised_a, config_a)
    delta_b = compute_deltas(normalised_b, config_b)
    pd.testing.assert_frame_equal(delta_a, delta_b)

    coefficients_a = analyzer._stage_compute_coefficients(delta_a, config_a.rho)
    coefficients_b = compute_coefficients(delta_b, config_b.rho)
    pd.testing.assert_frame_equal(coefficients_a, coefficients_b)

    grades_a = analyzer._stage_compute_grades(coefficients_a)
    grades_b = compute_grades(coefficients_b)
    pd.testing.assert_series_equal(grades_a, grades_b)
    assert analyzer._stage_rank_factors(grades_a) == rank_factors(grades_b)


def test_numeric_inspection_keeps_previous_threshold_semantics():
    dataframe = pd.DataFrame(
        {
            "good": [1, 2, 3, 4, 5],
            "exact80": [1, 2, 3, 4, "bad"],
            "too_sparse": [1, 2, np.nan, np.nan, np.nan],
            "infinite": [1, 2, 3, np.inf, 5],
            "labels": ["a", "b", "c", "d", "e"],
        }
    )

    columns, quality = detect_reliable_numeric_columns(dataframe)
    assert columns == ["good", "exact80", "infinite"]
    assert quality["good"] == (5, 5, 1.0)
    assert quality["exact80"] == (4, 5, 0.8)
    assert quality["infinite"] == (4, 5, 0.8)
    assert quality["too_sparse"] == (2, 5, 0.4)


def test_result_helpers_preserve_network_and_radar_payloads():
    result = GreyRelationalAnalyzer().run(_dataframe(), _config())

    scores, limited = limited_network_scores(result, max_factors=1)
    assert limited is True
    assert list(scores) == [result.ranked_factors[0]]
    assert math.isclose(scores[result.ranked_factors[0]], result.grg_series[result.ranked_factors[0]])

    categories, data, radar_limited = radar_payload(
        result,
        result.config.comparative_column_names,
        max_samples=2,
    )
    assert categories == result.config.comparative_column_names
    assert radar_limited is True
    assert list(data) == ["A", "B"]
    assert len(data["A"]) == len(categories)


def test_table_model_clipboard_serializers_keep_display_format():
    dataframe = pd.DataFrame({"A": [1.23456, 2.0], "B": ["x", "y"]})
    model = PandasTableModel(dataframe)

    full_text, rows, cols = model_to_tsv(model)
    assert rows == 2
    assert cols == 3  # reset_index(drop=False) preserves the historical index column
    assert "1.2346" in full_text

    indexes = [model.index(0, 1), model.index(0, 2)]
    selected_text, cell_count = selected_indexes_to_tsv(model, indexes)
    assert cell_count == 2
    assert selected_text.splitlines()[0] == "A\tB"
    assert selected_text.splitlines()[1] == "1.2346\tx"


def test_radar_widget_reuses_plot_canvas_export_host():
    app = QApplication.instance() or QApplication([])
    widget = RadarWidget()
    widget.plot(
        categories=["A", "B", "C"],
        data_dict={"S1": [0.1, 0.5, 0.9]},
        title="Profiles",
    )
    assert widget.get_figure() is not None
    widget.clear()
    assert widget.get_figure() is None
    widget.deleteLater()
    app.processEvents()
