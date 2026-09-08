# -*- coding: utf-8 -*-
"""Radar chart widget built on the shared Matplotlib figure canvas."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget

from ui.widgets.plot_canvas import PlotCanvas
from utils.plot_styler import plot_radar_chart


class RadarWidget(PlotCanvas):
    """Specialised PlotCanvas that builds normalised sample-profile radar charts."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            parent=parent,
            show_toolbar=False,
            default_filename="gra_sample_profiles",
            placeholder_text="Run analysis to display sample profiles.",
        )
        self.setMinimumSize(300, 300)

    def plot(
        self,
        categories: list[str],
        data_dict: dict[str, list[float]],
        title: str = "Normalised sample profiles",
    ) -> None:
        """Build and display a radar chart using the shared publication style."""
        figure = plot_radar_chart(
            categories=list(categories),
            data_dict={str(key): list(values) for key, values in data_dict.items()},
            title=title,
        )
        self.display_figure(figure)
