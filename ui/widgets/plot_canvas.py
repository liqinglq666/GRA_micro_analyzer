# -*- coding: utf-8 -*-
"""Matplotlib canvas widget for embedding and exporting publication figures."""

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

from utils.plot_styler import export_figure


class PlotCanvas(QWidget):
    """Reusable Matplotlib figure host with a shared publication export flow."""

    cell_hovered = Signal(str, str, float)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        show_toolbar: bool = True,
        default_filename: str = "gra_figure",
        placeholder_text: str = "Run analysis to display chart.",
    ) -> None:
        super().__init__(parent)
        self._figure: Optional[Figure] = None
        self._canvas: Optional[FigureCanvas] = None
        self._show_toolbar = show_toolbar
        self._default_filename = default_filename
        self._placeholder_text = placeholder_text

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._placeholder = self._make_placeholder(self._placeholder_text)
        self._layout.addWidget(self._placeholder)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def display_figure(self, figure: Figure) -> None:
        """Replace the current content with *figure*."""
        self._clear_layout_widgets()
        self._figure = figure

        canvas = FigureCanvas(figure)
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self._canvas = canvas
        self._layout.addWidget(canvas)
        canvas.draw()

    def clear(self, message: Optional[str] = None) -> None:
        """Remove the current figure and restore a placeholder message."""
        self._clear_layout_widgets()
        self._figure = None
        self._canvas = None
        self._placeholder = self._make_placeholder(message or self._placeholder_text)
        self._layout.addWidget(self._placeholder)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._canvas is not None:
            self._canvas.draw_idle()

    def prompt_save_figure(self, parent: Optional[QWidget] = None) -> None:
        """Export the current figure through the shared publication pipeline."""
        if self._figure is None:
            QMessageBox.information(parent or self, "No Figure", "Run analysis first.")
            return

        path_str, selected_filter = QFileDialog.getSaveFileName(
            parent or self,
            "Save Publication Figure",
            f"{self._default_filename}.svg",
            "SVG Vector (*.svg);;PDF Vector (*.pdf);;PNG 600 dpi (*.png)",
        )
        if not path_str:
            return

        path = Path(path_str)
        fmt = self._format_from_filter(selected_filter, path)
        try:
            saved = export_figure(self._figure, path, fmt=fmt)
            QMessageBox.information(
                parent or self,
                "Saved",
                f"Publication figure saved to:\n{saved}\n\n"
                "SVG/PDF are vector formats; PNG is exported at 600 dpi.",
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(parent or self, "Save Failed", str(exc))

    def get_figure(self) -> Optional[Figure]:
        return self._figure

    def _clear_layout_widgets(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)  # type: ignore[call-overload]
                widget.deleteLater()

    @staticmethod
    def _make_placeholder(message: str) -> QLabel:
        label = QLabel(message)
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

    def _on_mouse_move(self, event) -> None:
        if event.inaxes is None:
            return
        ax = event.inaxes
        images = ax.get_images()
        if not images:
            return
        image = images[0]
        data = image.get_array()
        if data is None or event.xdata is None or event.ydata is None:
            return

        col_idx = int(round(event.xdata))
        row_idx = int(round(event.ydata))
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
