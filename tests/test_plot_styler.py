from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from utils.plot_styler import (
    _network_linewidth,
    apply_sci_style,
    build_coefficient_heatmap,
    build_grg_bar_chart,
    export_figure,
    plot_network_diagram,
    plot_radar_chart,
)


def test_publication_style_uses_high_resolution_and_embeddable_fonts():
    apply_sci_style()
    assert matplotlib.rcParams["savefig.dpi"] == 600
    assert matplotlib.rcParams["pdf.fonttype"] == 42
    assert matplotlib.rcParams["svg.fonttype"] == "none"


def test_grg_chart_uses_fixed_absolute_scale():
    series = pd.Series({"A": 0.81, "B": 0.80, "C": 0.55})
    fig = build_grg_bar_chart(series)
    ax = fig.axes[0]
    x_min, x_max = ax.get_xlim()
    assert x_min == 0.0
    assert np.isclose(x_max, 1.02)
    assert len(ax.patches) == 3


def test_heatmap_suppresses_cell_text_when_matrix_is_large():
    small = pd.DataFrame(np.full((4, 4), 0.7))
    large = pd.DataFrame(np.full((20, 20), 0.7))

    small_fig = build_coefficient_heatmap(small)
    large_fig = build_coefficient_heatmap(large)

    assert len(small_fig.axes[0].texts) == 16
    assert len(large_fig.axes[0].texts) == 0


def test_network_linewidth_is_absolute_not_dataset_rescaled():
    assert np.isclose(_network_linewidth(0.80), 2.54)
    assert np.isclose(_network_linewidth(0.81), 2.563)
    assert _network_linewidth(0.81) > _network_linewidth(0.80)
    assert _network_linewidth(1.0) <= 3.0


def test_network_and_radar_figures_build_without_pyplot_state():
    network = plot_network_diagram(
        "Target",
        {"Porosity": 0.78, "Bound water": 0.74, "Crystallinity": 0.61},
    )
    radar = plot_radar_chart(
        ["Porosity", "Bound water", "Crystallinity"],
        {"S1": [0.2, 0.8, 0.5], "S2": [0.4, 0.6, 0.9]},
    )
    assert network.axes
    assert radar.axes
    assert radar.axes[0].name == "polar"


def test_export_supports_svg_pdf_and_600_dpi_png(tmp_path: Path):
    fig = build_grg_bar_chart(pd.Series({"A": 0.8, "B": 0.6}))
    for fmt in ("svg", "pdf", "png"):
        output = export_figure(fig, tmp_path / "figure", fmt=fmt)
        assert output.exists()
        assert output.suffix == f".{fmt}"
        assert output.stat().st_size > 0
