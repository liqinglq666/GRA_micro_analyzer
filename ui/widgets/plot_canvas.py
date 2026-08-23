# -*- coding: utf-8 -*-
"""
ui/widgets/plot_canvas.py
Matplotlib canvas widget for embedding plots in PySide6 windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class PlotCanvas(QWidget):
    """Embeds a Matplotlib Figure directly inside a PySide6 widget."""

    cell_hovered = Signal(str, str, float)   # row_label, col_label, value

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        show_toolbar: bool = True,
    ) -> None:
        super().__init__(parent)

        self._figure: Optional[Figure] = None
        self._canvas: Optional[FigureCanvas] = None
        self._show_toolbar = show_toolbar

        self._placeholder = QLabel("Run analysis to display chart.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; font-size: 10pt;")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addWidget(self._placeholder)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def display_figure(self, figure: Figure) -> None:
        """Bind *figure* to a brand-new FigureCanvasQTAgg and display it."""
        self._clear_layout_widgets()
        self._figure = figure

        canvas = FigureCanvas(figure)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

        self._canvas = canvas
        self._layout.addWidget(canvas)
        canvas.draw()

    def clear(self, message: str = "Run analysis to display chart.") -> None:
        """Remove the current figure and restore the placeholder message."""
        self._clear_layout_widgets()
        self._figure = None
        self._canvas = None
        self._placeholder = QLabel(message)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; font-size: 10pt;")
        self._layout.addWidget(self._placeholder)

    def resizeEvent(self, event) -> None:   # type: ignore[override]
        """Redraw the canvas whenever the widget is resized."""
        super().resizeEvent(event)
        if self._canvas is not None:
            self._canvas.draw_idle()

    def prompt_save_figure(self, parent: Optional[QWidget] = None) -> None:
        """Open a save dialog and export the current figure."""
        if self._figure is None:
            QMessageBox.information(parent or self, "No Figure", "Run analysis first.")
            return

        path_str, selected_filter = QFileDialog.getSaveFileName(
            parent or self,
            "Save Figure",
            "figure.svg",
            "SVG Image (*.svg);;PDF Document (*.pdf);;PNG Image (*.png)",
        )
        if not path_str:
            return

        suffix = self._suffix_from_filter(selected_filter)
        path = Path(path_str)
        if path.suffix.lower() not in {".svg", ".pdf", ".png"}:
            path = path.with_suffix(suffix)

        try:
            self._figure.savefig(path, bbox_inches="tight")
            QMessageBox.information(parent or self, "Saved", f"Figure saved to:\n{path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(parent or self, "Save Failed", str(exc))

    def get_figure(self) -> Optional[Figure]:
        return self._figure

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_layout_widgets(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)   # type: ignore[call-overload]
                w.deleteLater()

    @staticmethod
    def _suffix_from_filter(selected_filter: str) -> str:
        if "PDF" in selected_filter:
            return ".pdf"
        if "PNG" in selected_filter:
            return ".png"
        return ".svg"

    # ------------------------------------------------------------------
    # Heatmap hover detection
    # ------------------------------------------------------------------

    def _on_mouse_move(self, event) -> None:
        if event.inaxes is None:
            return
        ax = event.inaxes
        images = ax.get_images()
        if not images:
            return
        im = images[0]
        data = im.get_array()
        if data is None:
            return
        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return
        col_idx = int(round(x))
        row_idx = int(round(y))
        n_rows, n_cols = data.shape
        if not (0 <= row_idx < n_rows and 0 <= col_idx < n_cols):
            return
        value = float(data[row_idx, col_idx])
        x_ticks = ax.get_xticklabels()
        y_ticks = ax.get_yticklabels()
        col_label = (
            x_ticks[col_idx].get_gid() or x_ticks[col_idx].get_text()
            if col_idx < len(x_ticks)
            else str(col_idx)
        )
        row_label = y_ticks[row_idx].get_text() if row_idx < len(y_ticks) else str(row_idx)
        self.cell_hovered.emit(row_label, col_label, value)
