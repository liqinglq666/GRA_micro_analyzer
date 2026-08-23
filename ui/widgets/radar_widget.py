# -*- coding: utf-8 -*-
"""
ui/widgets/radar_widget.py
==========================
Self-contained radar (spider) chart widget for PySide6.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QResizeEvent,
)
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_PALETTE = [
    QColor("#1F77B4"), QColor("#FF7F0E"), QColor("#2CA02C"), QColor("#D62728"),
    QColor("#9467BD"), QColor("#8C564B"), QColor("#E377C2"), QColor("#7F7F7F"),
    QColor("#BCBD22"), QColor("#17BECF"),
]
_GRID_LEVELS = 5
_FILL_ALPHA = 60
_GRID_COLOUR = QColor("#BBBBBB")
_LABEL_COLOUR = QColor("#333333")
_BG_COLOUR = QColor("#FFFFFF")
_TICK_COLOUR = QColor("#999999")
_MAX_LABEL_LEN = 14


class RadarWidget(QWidget):
    """QPainter-based radar / spider chart widget."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 300)

        self._categories: list[str] = []
        self._data_dict: dict[str, list[float]] = {}
        self._title: str = ""
        self._has_data: bool = False

        self._placeholder = QLabel("Run analysis to display Radar Chart.", self)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; font-size: 10pt;")
        self._placeholder.setGeometry(self.rect())
        self._placeholder.show()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plot(
        self,
        categories: list[str],
        data_dict: dict[str, list[float]],
        title: str = "Optimization Envelope - Normalised Sample Profiles",
    ) -> None:
        """Draw or redraw the radar chart."""
        self._categories = list(categories)
        self._data_dict = {str(k): list(v) for k, v in data_dict.items()}
        self._title = title
        self._has_data = True
        self._placeholder.hide()
        self.update()

    def clear(self) -> None:
        """Reset to placeholder state."""
        self._categories = []
        self._data_dict = {}
        self._title = ""
        self._has_data = False
        self._placeholder.show()
        self.update()

    def prompt_save_figure(self, parent: Optional[QWidget] = None) -> None:
        """Open a save dialog and export the chart as SVG or PNG."""
        if not self._has_data:
            QMessageBox.information(
                parent or self, "No Chart", "Run analysis first to generate a chart."
            )
            return
        path_str, selected_filter = QFileDialog.getSaveFileName(
            parent or self,
            "Save Radar Chart",
            "radar_chart.svg",
            "SVG Image (*.svg);;PNG Image (*.png)",
        )
        if not path_str:
            return

        suffix = ".png" if "PNG" in selected_filter else ".svg"
        path = Path(path_str)
        if path.suffix.lower() not in {".svg", ".png"}:
            path = path.with_suffix(suffix)

        try:
            if path.suffix.lower() == ".svg":
                self._save_svg(str(path))
            else:
                self.grab().save(str(path))
            QMessageBox.information(parent or self, "Saved", f"Radar chart saved to:\n{path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(parent or self, "Save Failed", str(exc))
            logger.exception("RadarWidget save failed.")

    def get_figure(self):
        """Stub kept for API compatibility with PlotCanvas. Returns None."""
        return None

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._placeholder.setGeometry(self.rect())

    def paintEvent(self, _event) -> None:
        if not self._has_data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw(painter, self.width(), self.height())
        painter.end()

    # ------------------------------------------------------------------
    # Drawing core
    # ------------------------------------------------------------------

    def _draw(self, painter: QPainter, w: int, h: int) -> None:
        n = len(self._categories)
        painter.fillRect(0, 0, w, h, _BG_COLOUR)

        if n < 3:
            painter.setPen(_LABEL_COLOUR)
            painter.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                f"At least 3 comparative factors are required (got {n}).",
            )
            return

        title_h = 36
        legend_h = self._legend_height()
        margin = 70
        cx = w / 2.0
        available_h = h - title_h - legend_h - 2 * margin
        cy = title_h + margin + available_h / 2.0
        radius = min(w / 2.0 - margin, available_h / 2.0)
        if radius < 20:
            return

        self._draw_title(painter, w, title_h)

        angles = [math.radians(-90.0 + 360.0 * i / n) for i in range(n)]
        self._draw_grid(painter, cx, cy, radius, angles)
        self._draw_labels(painter, cx, cy, radius, angles)
        self._draw_series(painter, cx, cy, radius, angles)

        sample_ids = list(self._data_dict.keys())
        if len(sample_ids) > 1:
            self._draw_legend(painter, sample_ids, w, h, legend_h)

    def _draw_title(self, painter: QPainter, w: int, title_h: int) -> None:
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        painter.setFont(title_font)
        painter.setPen(_LABEL_COLOUR)
        painter.drawText(
            QRectF(0, 6, w, title_h),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self._title,
        )

    def _draw_grid(self, painter: QPainter, cx: float, cy: float, radius: float, angles: list[float]) -> None:
        grid_pen = QPen(_GRID_COLOUR)
        grid_pen.setWidth(1)
        grid_pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(grid_pen)

        for level in range(1, _GRID_LEVELS + 1):
            r = radius * level / _GRID_LEVELS
            ring_pts = QPolygonF([
                QPointF(cx + r * math.cos(a), cy + r * math.sin(a))
                for a in angles
            ])
            ring_pts.append(ring_pts[0])
            painter.drawPolyline(ring_pts)

        spoke_pen = QPen(_GRID_COLOUR)
        spoke_pen.setWidth(1)
        spoke_pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(spoke_pen)
        for a in angles:
            painter.drawLine(
                QPointF(cx, cy),
                QPointF(cx + radius * math.cos(a), cy + radius * math.sin(a)),
            )

        tick_font = QFont()
        tick_font.setPointSize(7)
        painter.setFont(tick_font)
        painter.setPen(_TICK_COLOUR)
        a0 = angles[0]
        for level in range(1, _GRID_LEVELS + 1):
            r = radius * level / _GRID_LEVELS
            tx = cx + r * math.cos(a0) + 3
            ty = cy + r * math.sin(a0)
            painter.drawText(QPointF(tx, ty), f"{level / _GRID_LEVELS:.1f}")

    def _draw_labels(self, painter: QPainter, cx: float, cy: float, radius: float, angles: list[float]) -> None:
        label_font = QFont()
        label_font.setPointSize(9)
        painter.setFont(label_font)
        painter.setPen(_LABEL_COLOUR)
        label_pad = 16
        rect_w, rect_h = 96, 32

        for cat, a in zip(self._categories, angles):
            lx = cx + (radius + label_pad) * math.cos(a)
            ly = cy + (radius + label_pad) * math.sin(a)
            txt = cat if len(cat) <= _MAX_LABEL_LEN else cat[:_MAX_LABEL_LEN - 1] + "…"
            txt = txt.replace("_", " ")
            cos_a, sin_a = math.cos(a), math.sin(a)
            rx = lx if cos_a > 0.15 else lx - rect_w if cos_a < -0.15 else lx - rect_w / 2.0
            ry = ly if sin_a > 0.15 else ly - rect_h if sin_a < -0.15 else ly - rect_h / 2.0
            painter.drawText(QRectF(rx, ry, rect_w, rect_h), Qt.AlignmentFlag.AlignCenter, txt)

    def _draw_series(self, painter: QPainter, cx: float, cy: float, radius: float, angles: list[float]) -> None:
        n = len(self._categories)
        for s_idx, sid in enumerate(self._data_dict.keys()):
            colour = _PALETTE[s_idx % len(_PALETTE)]
            raw_vals = self._data_dict[sid]
            padded = (raw_vals + [0.0] * n)[:n]
            vals = [max(0.0, min(1.0, float(v))) for v in padded]

            pts = QPolygonF([
                QPointF(
                    cx + radius * vals[i] * math.cos(angles[i]),
                    cy + radius * vals[i] * math.sin(angles[i]),
                )
                for i in range(n)
            ])
            pts.append(pts[0])

            fill_colour = QColor(colour)
            fill_colour.setAlpha(_FILL_ALPHA)
            path = QPainterPath()
            path.addPolygon(pts)
            painter.fillPath(path, fill_colour)

            line_pen = QPen(colour)
            line_pen.setWidthF(1.8)
            painter.setPen(line_pen)
            painter.drawPolyline(pts)

            dot_pen = QPen(Qt.GlobalColor.white)
            dot_pen.setWidthF(1.2)
            painter.setPen(dot_pen)
            painter.setBrush(colour)
            for i in range(n):
                painter.drawEllipse(pts[i], 4.0, 4.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)

    # ------------------------------------------------------------------
    # Legend
    # ------------------------------------------------------------------

    def _legend_height(self) -> int:
        n = len(self._data_dict)
        if n <= 1:
            return 0
        cols = min(n, 4)
        rows = math.ceil(n / cols)
        return rows * 22 + 12

    def _draw_legend(
        self,
        painter: QPainter,
        sample_ids: list[str],
        w: int,
        h: int,
        legend_h: int,
    ) -> None:
        cols = min(len(sample_ids), 4)
        cell_w = w / cols
        cell_h = 22
        y0 = h - legend_h + 6
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        for idx, sid in enumerate(sample_ids):
            colour = _PALETTE[idx % len(_PALETTE)]
            col = idx % cols
            row = idx // cols
            x = col * cell_w + 12
            y = y0 + row * cell_h
            painter.setBrush(colour)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(x, y + 5, 12, 12))
            painter.setPen(_LABEL_COLOUR)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawText(
                QRectF(x + 18, y, cell_w - 22, cell_h),
                Qt.AlignmentFlag.AlignVCenter,
                sid,
            )

    # ------------------------------------------------------------------
    # SVG export
    # ------------------------------------------------------------------

    def _save_svg(self, path_str: str) -> None:
        generator = QSvgGenerator()
        generator.setFileName(path_str)
        generator.setSize(self.size())
        generator.setViewBox(self.rect())
        generator.setTitle(self._title)
        painter = QPainter(generator)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw(painter, self.width(), self.height())
        painter.end()
