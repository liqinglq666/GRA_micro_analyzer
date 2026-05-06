# -*- coding: utf-8 -*-
"""
ui/widgets/plot_canvas.py
Matplotlib canvas widget for embedding plots in PySide6 windows.

KEY DESIGN RULE
---------------
__init__ does NOT create any matplotlib Figure or FigureCanvas.
display_figure() creates the one and only FigureCanvas for a given
Figure and sizes it to fill this widget, redrawing on every resize.
"""

from __future__ import annotations

from typing import Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)


class PlotCanvas(QWidget):
    """
    Embeds a Matplotlib Figure directly inside a PySide6 widget.

    The canvas expands to fill the entire widget area and redraws
    automatically whenever the widget is resized, so charts always
    use the available screen space.

    No Figure or FigureCanvas is created in __init__.
    """

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

        # Placeholder shown before any figure is displayed
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
        """
        Bind *figure* to a brand-new FigureCanvasQTAgg and display it,
        filling this widget's current size.

        The canvas is set to Expanding so it stretches with the window.
        A matplotlib resize callback keeps the Figure in sync when the
        widget is resized.
        """
        # Remove whatever is currently in the layout
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)   # type: ignore[call-overload]
                w.deleteLater()

        self._figure = figure

        canvas = FigureCanvas(figure)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

        self._canvas = canvas
        self._layout.addWidget(canvas)

        # Force an immediate synchronous render
        canvas.draw()

    def resizeEvent(self, event) -> None:   # type: ignore[override]
        """Redraw the canvas whenever the widget is resized."""
        super().resizeEvent(event)
        if self._canvas is not None:
            self._canvas.draw_idle()

    def prompt_save_figure(self, parent: Optional[QWidget] = None) -> None:
        """Open a save dialog and export the current figure."""
        if self._figure is None:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            parent or self,
            "Save Figure",
            "figure",
            "SVG Image (*.svg);;PDF Document (*.pdf);;PNG Image (*.png)",
        )
        if not path_str:
            return
        self._figure.savefig(path_str, bbox_inches="tight")

    def get_figure(self) -> Optional[Figure]:
        return self._figure

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
        x_labels = [t.get_text() for t in ax.get_xticklabels()]
        y_labels = [t.get_text() for t in ax.get_yticklabels()]
        col_label = x_labels[col_idx] if col_idx < len(x_labels) else str(col_idx)
        row_label = y_labels[row_idx] if row_idx < len(y_labels) else str(row_idx)
        self.cell_hovered.emit(row_label, col_label, value)
