# -*- coding: utf-8 -*-
"""Matplotlib-backed radar chart widget for consistent manuscript export."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.plot_styler import export_figure, plot_radar_chart

logger = logging.getLogger(__name__)


class RadarWidget(QWidget):
    """Radar chart widget using the same Matplotlib styling as all other figures."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 300)

        self._figure: Optional[Figure] = None
        self._canvas: Optional[FigureCanvas] = None
        self._categories: list[str] = []
        self._data_dict: dict[str, list[float]] = {}
        self._title = ""

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._placeholder = self._make_placeholder()
        self._layout.addWidget(self._placeholder)

    def plot(
        self,
        categories: list[str],
        data_dict: dict[str, list[float]],
        title: str = "Normalised sample profiles",
    ) -> None:
        self._categories = list(categories)
        self._data_dict = {str(key): list(values) for key, values in data_dict.items()}
        self._title = title

        figure = plot_radar_chart(
            categories=self._categories,
            data_dict=self._data_dict,
            title=self._title,
        )
        self._display_figure(figure)

    def clear(self) -> None:
        self._categories = []
        self._data_dict = {}
        self._title = ""
        self._clear_layout_widgets()
        self._figure = None
        self._canvas = None
        self._placeholder = self._make_placeholder()
        self._layout.addWidget(self._placeholder)

    def prompt_save_figure(self, parent: Optional[QWidget] = None) -> None:
        if self._figure is None:
            QMessageBox.information(parent or self, "No Chart", "Run analysis first.")
            return

        path_str, selected_filter = QFileDialog.getSaveFileName(
            parent or self,
            "Save Publication Figure",
            "gra_sample_profiles.svg",
            "SVG Vector (*.svg);;PDF Vector (*.pdf);;PNG 600 dpi (*.png)",
        )
        if not path_str:
            return

        fmt = self._format_from_filter(selected_filter, Path(path_str))
        try:
            saved = export_figure(self._figure, path_str, fmt=fmt)
            QMessageBox.information(
                parent or self,
                "Saved",
                f"Publication figure saved to:\n{saved}\n\n"
                "SVG/PDF are vector formats; PNG is exported at 600 dpi.",
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(parent or self, "Save Failed", str(exc))
            logger.exception("Radar figure export failed.")

    def get_figure(self) -> Optional[Figure]:
        return self._figure

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._canvas is not None:
            self._canvas.draw_idle()

    def _display_figure(self, figure: Figure) -> None:
        self._clear_layout_widgets()
        self._figure = figure
        canvas = FigureCanvas(figure)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._canvas = canvas
        self._layout.addWidget(canvas)
        canvas.draw()

    def _clear_layout_widgets(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)  # type: ignore[call-overload]
                widget.deleteLater()

    def _make_placeholder(self) -> QLabel:
        label = QLabel("Run analysis to display sample profiles.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #777; font-size: 10pt;")
        return label

    @staticmethod
    def _format_from_filter(selected_filter: str, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf" or "PDF" in selected_filter:
            return "pdf"
        if suffix == ".png" or "PNG" in selected_filter:
            return "png"
        return "svg"
