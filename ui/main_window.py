# -*- coding: utf-8 -*-
# ui/main_window.py
"""
GRA-MicroAnalyzer — Main Application Window
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtCore import Qt, QAbstractTableModel, QElapsedTimer, QModelIndex, QPersistentModelIndex
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.data_model import GRAConfig, GRAResult
from ui.threads import GRAWorker
from ui.widgets.config_panel import ConfigPanel
from ui.widgets.plot_canvas import PlotCanvas
from ui.widgets.radar_widget import RadarWidget
from utils.file_io import save_results_to_excel
from utils.plot_styler import (
    build_coefficient_heatmap,
    build_grg_bar_chart,
    plot_network_diagram,
)

logger = logging.getLogger(__name__)

_PREVIEW_ROW_LIMIT = 1_000
_WINDOW_TITLE = "GRA-MicroAnalyzer — Grey Relational Analysis for Microstructural Attribution"
_MIN_WIDTH = 1400
_MIN_HEIGHT = 800
_LEFT_PANEL_MAX_WIDTH = 320
_HEATMAP_MAX_ANNOTATED_CELLS = 2_000
_NETWORK_MAX_FACTORS = 40
_RADAR_MAX_SAMPLES = 8


# ---------------------------------------------------------------------------
# Pandas -> Qt Table Model
# ---------------------------------------------------------------------------


class _PandasTableModel(QAbstractTableModel):
    """Minimal read-only QAbstractTableModel adapter for a Pandas DataFrame."""

    def __init__(self, dataframe: pd.DataFrame, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._df = dataframe.head(_PREVIEW_ROW_LIMIT).reset_index(drop=False)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self._df)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self._df.columns)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._df.iat[index.row(), index.column()]
            if isinstance(value, float):
                return f"{value:.4f}"
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            value = self._df.iat[index.row(), index.column()]
            if isinstance(value, (int, float)):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """Top-level application window for GRA-MicroAnalyzer."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._dataframe: Optional[pd.DataFrame] = None
        self._last_result: Optional[GRAResult] = None
        self._worker: Optional[GRAWorker] = None
        self._worker_running = False
        self._analysis_failed = False
        self._run_timer = QElapsedTimer()

        self._setup_window()
        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._connect_signals()

        logger.info("MainWindow initialised.")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle(_WINDOW_TITLE)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self.resize(1600, 900)

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        action_load = QAction("&Load Dataset…", self)
        action_load.setShortcut("Ctrl+O")
        action_load.setStatusTip("Open a CSV or Excel data file.")
        action_load.triggered.connect(self._action_load_dataset)

        self._action_save = QAction("&Save Results…", self)
        self._action_save.setShortcut("Ctrl+S")
        self._action_save.setStatusTip("Export GRA results to an Excel workbook.")
        self._action_save.setEnabled(False)
        self._action_save.triggered.connect(self._action_save_results)

        action_quit = QAction("&Quit", self)
        action_quit.setShortcut("Ctrl+Q")
        action_quit.triggered.connect(QApplication.quit)

        file_menu.addAction(action_load)
        file_menu.addAction(self._action_save)
        file_menu.addSeparator()
        file_menu.addAction(action_quit)

        help_menu = menu_bar.addMenu("&Help")
        action_about = QAction("&About GRA-MicroAnalyzer", self)
        action_about.triggered.connect(self._action_show_about)
        help_menu.addAction(action_about)

    def _setup_central_widget(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._config_panel = ConfigPanel()
        self._config_panel.setMaximumWidth(_LEFT_PANEL_MAX_WIDTH)
        self._config_panel.setMinimumWidth(300)
        splitter.addWidget(self._config_panel)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_preview_tab(), "[1] Data Preview")
        self._tabs.addTab(self._build_results_tab(), "[2] GRG Results")
        self._tabs.addTab(self._build_heatmap_tab(), "[3] Coefficient Heatmap")
        self._tabs.addTab(self._build_network_tab(), "[4] Network Diagram")
        self._tabs.addTab(self._build_radar_tab(), "[5] Radar Chart")

        splitter.addWidget(self._tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 1280])
        self.setCentralWidget(splitter)

    def _setup_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setMaximumHeight(16)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._status_bar.addPermanentWidget(self._progress_bar)
        self._status_bar.showMessage("Ready — load a dataset to begin.")

    # ------------------------------------------------------------------
    # Tab Builders
    # ------------------------------------------------------------------

    def _build_preview_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QToolBar("Preview Actions")
        toolbar.setMovable(False)
        action_copy_sel = QAction("Copy Selection", self)
        action_copy_sel.setShortcut(QKeySequence.StandardKey.Copy)
        action_copy_sel.triggered.connect(self._copy_selection_to_clipboard)
        toolbar.addAction(action_copy_sel)

        action_copy_all = QAction("Copy All", self)
        action_copy_all.setShortcut(QKeySequence("Ctrl+Shift+C"))
        action_copy_all.triggered.connect(self._copy_all_to_clipboard)
        toolbar.addAction(action_copy_all)
        layout.addWidget(toolbar)

        self._preview_notice = QLabel()
        self._preview_notice.setStyleSheet("background: #FFF3CD; color: #856404; padding: 4px; font-size: 8pt;")
        self._preview_notice.setVisible(False)
        layout.addWidget(self._preview_notice)

        self._table_view_widget = QTableView()
        self._table_view_widget.setAlternatingRowColors(True)
        self._table_view_widget.horizontalHeader().setStretchLastSection(True)
        self._table_view_widget.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)  # type: ignore[attr-defined]
        self._table_view_widget.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)  # type: ignore[attr-defined]
        layout.addWidget(self._table_view_widget)
        return container

    def _build_results_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._plot_canvas_grg = PlotCanvas(show_toolbar=False)
        layout.addWidget(self._plot_canvas_grg)
        layout.addWidget(self._build_export_bar(tab="bar"))
        return container

    def _build_heatmap_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._plot_canvas_heatmap = PlotCanvas(show_toolbar=False)
        self._plot_canvas_heatmap.cell_hovered.connect(self._on_heatmap_cell_hovered)
        layout.addWidget(self._plot_canvas_heatmap)
        layout.addWidget(self._build_export_bar(tab="heatmap"))
        return container

    def _build_network_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._plot_canvas_network = PlotCanvas(show_toolbar=False)
        layout.addWidget(self._plot_canvas_network)
        layout.addWidget(self._build_export_bar(tab="network"))
        return container

    def _build_radar_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._radar_widget = RadarWidget()
        layout.addWidget(self._radar_widget)
        layout.addWidget(self._build_export_bar(tab="radar"))
        return container

    def _build_export_bar(self, tab: str) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(34)
        h_layout = QHBoxLayout(bar)
        h_layout.setContentsMargins(8, 2, 8, 2)
        h_layout.setSpacing(8)

        h_layout.addWidget(QLabel("Export:"))

        btn_excel = QPushButton("Results to Excel (.xlsx)")
        btn_excel.setEnabled(False)
        btn_excel.setFixedHeight(26)
        btn_excel.clicked.connect(self._action_save_results)
        h_layout.addWidget(btn_excel)

        if tab == "heatmap":
            btn_fig = QPushButton("Save Heatmap (SVG / PDF / PNG)")
            btn_fig.clicked.connect(lambda: self._plot_canvas_heatmap.prompt_save_figure(self))
            self._btn_save_heatmap_fig = btn_fig
            self._btn_export_excel_heatmap_tab = btn_excel
        elif tab == "network":
            btn_fig = QPushButton("Save Network (SVG / PDF / PNG)")
            btn_fig.clicked.connect(lambda: self._plot_canvas_network.prompt_save_figure(self))
            self._btn_save_network_fig = btn_fig
            self._btn_export_excel_network_tab = btn_excel
        elif tab == "radar":
            btn_fig = QPushButton("Save Radar (SVG / PNG)")
            btn_fig.clicked.connect(lambda: self._radar_widget.prompt_save_figure(self))
            self._btn_save_radar_fig = btn_fig
            self._btn_export_excel_radar_tab = btn_excel
        else:
            btn_fig = QPushButton("Save Chart (SVG / PDF / PNG)")
            btn_fig.clicked.connect(lambda: self._plot_canvas_grg.prompt_save_figure(self))
            self._btn_save_grg_fig = btn_fig
            self._btn_export_excel = btn_excel

        btn_fig.setEnabled(False)
        btn_fig.setFixedHeight(26)
        h_layout.addWidget(btn_fig)
        h_layout.addStretch()
        return bar

    # ------------------------------------------------------------------
    # Signal Wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._config_panel.dataset_loaded.connect(self._on_dataset_loaded)
        self._config_panel.run_requested.connect(self._on_run_requested)
        self._config_panel.status_message.connect(self._status_bar.showMessage)

    # ------------------------------------------------------------------
    # Slots — ConfigPanel
    # ------------------------------------------------------------------

    def _on_dataset_loaded(self, dataframe: pd.DataFrame, file_path: Path) -> None:
        self._dataframe = dataframe
        self._last_result = None
        self._analysis_failed = False
        self._action_save.setEnabled(False)
        self._set_export_buttons_enabled(False)
        self._clear_result_views()

        model = _PandasTableModel(dataframe)
        self._table_view_widget.setModel(model)
        self._table_view_widget.resizeColumnsToContents()

        if len(dataframe) > _PREVIEW_ROW_LIMIT:
            self._preview_notice.setText(
                f"⚠ Preview capped at {_PREVIEW_ROW_LIMIT:,} rows. Full dataset ({len(dataframe):,} rows) is used for analysis."
            )
            self._preview_notice.setVisible(True)
        else:
            self._preview_notice.setVisible(False)

        self._tabs.setCurrentIndex(0)
        self.setWindowTitle(f"{file_path.name} — GRA-MicroAnalyzer")
        logger.info("Data preview updated — %d rows shown.", min(len(dataframe), _PREVIEW_ROW_LIMIT))

    def _on_run_requested(self, config: GRAConfig) -> None:
        if self._worker_running:
            QMessageBox.warning(self, "Analysis in Progress", "An analysis is already running.")
            return
        if self._dataframe is None:
            QMessageBox.critical(self, "No Data", "Load a dataset before running.")
            return
        self._start_worker(self._dataframe, config)

    # ------------------------------------------------------------------
    # Worker Management
    # ------------------------------------------------------------------

    def _start_worker(self, dataframe: pd.DataFrame, config: GRAConfig) -> None:
        self._worker = GRAWorker(dataframe=dataframe, config=config, parent=None)
        self._worker.progress_signal.connect(self._progress_bar.setValue)
        self._worker.log_signal.connect(self._status_bar.showMessage)
        self._worker.result_signal.connect(self._on_result_received)
        self._worker.error_signal.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._worker.deleteLater)

        self._worker_running = True
        self._analysis_failed = False
        self._run_timer.start()
        self._config_panel.set_running_state(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._clear_result_views()
        self._worker.start()
        logger.info("GRAWorker thread started.")

    def _on_result_received(self, result: GRAResult) -> None:
        """Called on the main thread when GRAWorker emits result_signal."""
        self._last_result = result
        self._analysis_failed = False
        self._action_save.setEnabled(True)
        self._set_export_buttons_enabled(True)

        ref_col = result.config.reference_column
        comp_cols = list(result.config.comparative_columns.keys())
        grg_dict = result.grg_series.to_dict()

        self._render_grg_chart(result, ref_col)
        self._render_heatmap(result, ref_col)
        self._render_network(result, ref_col, grg_dict)
        self._render_radar(result, ref_col, comp_cols)

        self._tabs.setCurrentIndex(1)
        logger.info(
            "Charts rendered — top factor: '%s' (GRG=%.4f).",
            result.top_factor,
            result.grg_series[result.top_factor],
        )

    def _render_grg_chart(self, result: GRAResult, ref_col: str) -> None:
        try:
            bar_fig = build_grg_bar_chart(
                grg_series=result.grg_series,
                title=f"Grey Relational Grade — Reference: {ref_col}",
            )
            self._plot_canvas_grg.display_figure(bar_fig)
            self._btn_save_grg_fig.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self._plot_canvas_grg.clear(f"Bar chart failed:\n{exc}")
            self._btn_save_grg_fig.setEnabled(False)
            logger.exception("Bar chart failed: %s", exc)

    def _render_heatmap(self, result: GRAResult, ref_col: str) -> None:
        n_rows, n_cols = result.coefficient_df.shape
        n_cells = n_rows * n_cols
        if n_cells > _HEATMAP_MAX_ANNOTATED_CELLS:
            self._plot_canvas_heatmap.clear(
                f"Heatmap skipped for responsiveness.\n"
                f"Matrix size: {n_rows:,} × {n_cols:,} = {n_cells:,} cells.\n"
                "Use Excel export to inspect the full coefficient matrix."
            )
            self._btn_save_heatmap_fig.setEnabled(False)
            logger.warning("Heatmap skipped: %d cells exceeds limit %d.", n_cells, _HEATMAP_MAX_ANNOTATED_CELLS)
            return
        try:
            heatmap_fig = build_coefficient_heatmap(
                coefficient_df=result.coefficient_df,
                title=f"Relational Coefficient Matrix — Reference: {ref_col}",
            )
            self._plot_canvas_heatmap.display_figure(heatmap_fig)
            self._btn_save_heatmap_fig.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self._plot_canvas_heatmap.clear(f"Heatmap failed:\n{exc}")
            self._btn_save_heatmap_fig.setEnabled(False)
            logger.exception("Heatmap failed: %s", exc)

    def _render_network(self, result: GRAResult, ref_col: str, grg_dict: dict[str, float]) -> None:
        if len(grg_dict) > _NETWORK_MAX_FACTORS:
            top_scores = result.grg_series.sort_values(ascending=False).head(_NETWORK_MAX_FACTORS).to_dict()
            self._status_bar.showMessage(
                f"Network diagram limited to top {_NETWORK_MAX_FACTORS} factors for readability."
            )
        else:
            top_scores = grg_dict
        try:
            network_fig = plot_network_diagram(
                target_name=ref_col,
                grg_scores=top_scores,
                title=f"Topology Network — Reference: {ref_col}",
            )
            self._plot_canvas_network.display_figure(network_fig)
            self._btn_save_network_fig.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self._plot_canvas_network.clear(f"Network diagram failed:\n{exc}")
            self._btn_save_network_fig.setEnabled(False)
            logger.exception("Network diagram failed: %s", exc)

    def _render_radar(self, result: GRAResult, ref_col: str, comp_cols: list[str]) -> None:
        try:
            norm_df = result.normalised_df
            available_comp = [c for c in comp_cols if c in norm_df.columns]
            sample_df = norm_df.head(_RADAR_MAX_SAMPLES)
            sample_ids = [str(i) for i in sample_df.index]
            data_dict = {
                sid: sample_df.iloc[idx][available_comp].astype(float).tolist()
                for idx, sid in enumerate(sample_ids)
            }
            title = f"Radar Chart — Reference: {ref_col}"
            if len(norm_df) > _RADAR_MAX_SAMPLES:
                title += f" (first {_RADAR_MAX_SAMPLES} samples)"
            self._radar_widget.plot(categories=available_comp, data_dict=data_dict, title=title)
            self._btn_save_radar_fig.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self._radar_widget.clear()
            self._btn_save_radar_fig.setEnabled(False)
            logger.exception("Radar chart failed: %s", exc)

    def _on_worker_error(self, message: str) -> None:
        self._analysis_failed = True
        QMessageBox.critical(self, "Analysis Error", message)
        self._status_bar.showMessage("Analysis failed — see error dialog.")
        logger.warning("Worker error: %s", message)

    def _on_heatmap_cell_hovered(self, row_label: str, col_label: str, value: float) -> None:
        self._status_bar.showMessage(f"Sample: {row_label} │ Factor: {col_label} │ ξ = {value:.4f}")

    def _on_worker_finished(self) -> None:
        elapsed_ms = self._run_timer.elapsed() if self._run_timer.isValid() else 0
        elapsed_str = f"{elapsed_ms / 1000:.2f} s" if elapsed_ms > 0 else "N/A"
        self._worker_running = False
        self._worker = None
        self._config_panel.set_running_state(False)
        self._progress_bar.setVisible(False)
        if self._analysis_failed:
            self._status_bar.showMessage(f"Analysis failed — elapsed: {elapsed_str}.")
        else:
            self._status_bar.showMessage(f"Analysis complete — elapsed: {elapsed_str}. Results ready for export.")
        logger.debug("GRAWorker thread finished — elapsed %s.", elapsed_str)

    # ------------------------------------------------------------------
    # Clipboard Helpers
    # ------------------------------------------------------------------

    def _copy_selection_to_clipboard(self) -> None:
        model = self._table_view_widget.model()
        if model is None:
            self._status_bar.showMessage("No data loaded — nothing to copy.")
            return
        selection_model = self._table_view_widget.selectionModel()
        if selection_model is None:
            return
        selection = selection_model.selectedIndexes()
        if not selection:
            self._status_bar.showMessage("No cells selected — use Ctrl+Shift+C to copy the entire table.")
            return
        cells = {
            (index.row(), index.column()): str(model.data(index, Qt.ItemDataRole.DisplayRole) or "")
            for index in selection
        }
        selected_rows = sorted({r for r, _ in cells})
        selected_cols = sorted({c for _, c in cells})
        headers = [
            str(model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or "")
            for col in selected_cols
        ]
        lines = ["\t".join(headers)]
        for row in selected_rows:
            lines.append("\t".join(cells.get((row, col), "") for col in selected_cols))
        QApplication.clipboard().setText("\n".join(lines))
        self._status_bar.showMessage(f"Copied {len(cells)} cell(s) to clipboard.")

    def _copy_all_to_clipboard(self) -> None:
        model = self._table_view_widget.model()
        if model is None:
            self._status_bar.showMessage("No data loaded — nothing to copy.")
            return
        n_rows = model.rowCount()
        n_cols = model.columnCount()
        headers = [
            str(model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or "")
            for col in range(n_cols)
        ]
        lines = ["\t".join(headers)]
        for row in range(n_rows):
            lines.append("\t".join(
                str(model.data(model.index(row, col), Qt.ItemDataRole.DisplayRole) or "")
                for col in range(n_cols)
            ))
        QApplication.clipboard().setText("\n".join(lines))
        self._status_bar.showMessage(f"Entire preview copied — {n_rows} rows × {n_cols} columns.")

    # ------------------------------------------------------------------
    # Export Button State
    # ------------------------------------------------------------------

    def _set_export_buttons_enabled(self, enabled: bool) -> None:
        self._btn_export_excel.setEnabled(enabled)
        self._btn_export_excel_heatmap_tab.setEnabled(enabled)
        self._btn_export_excel_network_tab.setEnabled(enabled)
        self._btn_export_excel_radar_tab.setEnabled(enabled)
        self._btn_save_grg_fig.setEnabled(enabled)
        self._btn_save_heatmap_fig.setEnabled(enabled)
        self._btn_save_network_fig.setEnabled(enabled)
        self._btn_save_radar_fig.setEnabled(enabled)

    def _clear_result_views(self) -> None:
        self._plot_canvas_grg.clear()
        self._plot_canvas_heatmap.clear()
        self._plot_canvas_network.clear()
        self._radar_widget.clear()

    # ------------------------------------------------------------------
    # Menu Action Handlers
    # ------------------------------------------------------------------

    def _action_load_dataset(self) -> None:
        self._config_panel._on_load_clicked()

    def _action_save_results(self) -> None:
        if self._last_result is None:
            QMessageBox.information(self, "No Results", "Run an analysis before exporting results.")
            return
        file_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results to Excel",
            "gra_results.xlsx",
            "Excel Workbook (*.xlsx)",
        )
        if not file_path_str:
            return
        try:
            saved_path = save_results_to_excel(result=self._last_result, output_path=file_path_str)
            QMessageBox.information(
                self,
                "Export Successful",
                f"Results exported to:\n{saved_path}\n\n"
                "Sheets:\n"
                "  1. GRG Ranking\n"
                "  2. Normalised Sequences\n"
                "  3. Delta Matrix\n"
                "  4. Xi Coefficient Matrix\n"
                "  5. Analysis Config",
            )
            self._status_bar.showMessage(f"Results saved: {saved_path.name}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export Failed", f"Could not save results:\n{exc}")
            logger.exception("Excel export failed.")

    def _action_show_about(self) -> None:
        QMessageBox.about(
            self,
            "About GRA-MicroAnalyzer",
            "<b>GRA-MicroAnalyzer</b> v1.0.0<br><br>"
            "Grey Relational Analysis for Microstructural Attribution<br>"
            "Designed for Material Science Researchers.<br><br>"
            "Built with PySide6, Pandas, NumPy, Matplotlib, and NetworkX.",
        )

    # ------------------------------------------------------------------
    # Window Events
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Analysis in Progress",
                "An analysis is currently running.\n\nClose after the worker finishes?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._worker.requestInterruption()
            self._worker.wait(3_000)
            if self._worker.isRunning():
                QMessageBox.information(
                    self,
                    "Still Running",
                    "The analysis is still running. The window will stay open to avoid corrupting the worker thread.",
                )
                event.ignore()
                return
        event.accept()
        logger.info("MainWindow closed.")
