# -*- coding: utf-8 -*-
"""Main application window for GRA-MicroAnalyzer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtCore import (
    QAbstractTableModel,
    QElapsedTimer,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)
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
_WINDOW_TITLE = "GRA-MicroAnalyzer — Microstructure–Property Association"
_MIN_WIDTH = 1320
_MIN_HEIGHT = 800
_LEFT_PANEL_MAX_WIDTH = 340
_HEATMAP_MAX_CELLS = 50_000
_NETWORK_MAX_FACTORS = 18
_RADAR_MAX_SAMPLES = 6


class _PandasTableModel(QAbstractTableModel):
    """Minimal read-only DataFrame adapter."""

    def __init__(self, dataframe: pd.DataFrame, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._df = dataframe.head(_PREVIEW_ROW_LIMIT).reset_index(drop=False)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self._df)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self._df.columns)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid():
            return None
        value = self._df.iat[index.row(), index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(value, float):
                return f"{value:.4f}"
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, (int, float)):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)


class MainWindow(QMainWindow):
    """Top-level desktop UI."""

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

    def _setup_window(self) -> None:
        self.setWindowTitle(_WINDOW_TITLE)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self.resize(1580, 900)

    def _setup_menu_bar(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        action_load = QAction("&Load Dataset…", self)
        action_load.setShortcut("Ctrl+O")
        action_load.setStatusTip("Open a CSV or Excel data file.")
        action_load.triggered.connect(self._action_load_dataset)

        self._action_save = QAction("&Export Results…", self)
        self._action_save.setShortcut("Ctrl+S")
        self._action_save.setStatusTip("Export GRA matrices, ranking, configuration, and data quality to Excel.")
        self._action_save.setEnabled(False)
        self._action_save.triggered.connect(self._action_save_results)

        action_quit = QAction("&Quit", self)
        action_quit.setShortcut("Ctrl+Q")
        action_quit.triggered.connect(QApplication.quit)

        file_menu.addAction(action_load)
        file_menu.addAction(self._action_save)
        file_menu.addSeparator()
        file_menu.addAction(action_quit)

        help_menu = self.menuBar().addMenu("&Help")
        action_about = QAction("&About GRA-MicroAnalyzer", self)
        action_about.triggered.connect(self._action_show_about)
        help_menu.addAction(action_about)

    def _setup_central_widget(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._config_panel = ConfigPanel()
        self._config_panel.setMinimumWidth(310)
        self._config_panel.setMaximumWidth(_LEFT_PANEL_MAX_WIDTH)
        splitter.addWidget(self._config_panel)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_preview_tab(), "Data")
        self._tabs.addTab(self._build_results_tab(), "GRG ranking")
        self._tabs.addTab(self._build_heatmap_tab(), "Coefficient map")
        self._tabs.addTab(self._build_network_tab(), "Association network")
        self._tabs.addTab(self._build_radar_tab(), "Sample profiles")

        splitter.addWidget(self._tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([330, 1250])
        self.setCentralWidget(splitter)

    def _setup_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(190)
        self._progress_bar.setMaximumHeight(16)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._status_bar.addPermanentWidget(self._progress_bar)
        self._status_bar.showMessage("Ready — load a dataset to begin.")

    def _build_preview_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QToolBar("Data actions")
        toolbar.setMovable(False)
        action_copy_sel = QAction("Copy selection", self)
        action_copy_sel.setShortcut(QKeySequence.StandardKey.Copy)
        action_copy_sel.triggered.connect(self._copy_selection_to_clipboard)
        toolbar.addAction(action_copy_sel)
        action_copy_all = QAction("Copy all", self)
        action_copy_all.setShortcut(QKeySequence("Ctrl+Shift+C"))
        action_copy_all.triggered.connect(self._copy_all_to_clipboard)
        toolbar.addAction(action_copy_all)
        layout.addWidget(toolbar)

        self._preview_notice = QLabel()
        self._preview_notice.setStyleSheet(
            "background: #FFF7E6; color: #6A531F; padding: 6px 8px; font-size: 8pt;"
        )
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
        self._plot_canvas_grg = PlotCanvas(
            show_toolbar=False,
            default_filename="gra_grg_ranking",
        )
        layout.addWidget(self._plot_canvas_grg)
        layout.addWidget(self._build_export_bar("bar"))
        return container

    def _build_heatmap_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._plot_canvas_heatmap = PlotCanvas(
            show_toolbar=False,
            default_filename="gra_coefficient_map",
        )
        self._plot_canvas_heatmap.cell_hovered.connect(self._on_heatmap_cell_hovered)
        layout.addWidget(self._plot_canvas_heatmap)
        layout.addWidget(self._build_export_bar("heatmap"))
        return container

    def _build_network_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._plot_canvas_network = PlotCanvas(
            show_toolbar=False,
            default_filename="gra_association_network",
        )
        layout.addWidget(self._plot_canvas_network)
        layout.addWidget(self._build_export_bar("network"))
        return container

    def _build_radar_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._radar_widget = RadarWidget()
        layout.addWidget(self._radar_widget)
        layout.addWidget(self._build_export_bar("radar"))
        return container

    def _build_export_bar(self, tab: str) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(42)
        bar.setStyleSheet("background: #F7F8FA; border-top: 1px solid #E3E6EA;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        note = QLabel("Publication export: SVG/PDF vector · PNG 600 dpi")
        note.setStyleSheet("color: #66707A; font-size: 8pt; border: none;")
        layout.addWidget(note)
        layout.addStretch()

        btn_excel = QPushButton("Excel results")
        btn_excel.setEnabled(False)
        btn_excel.setFixedHeight(28)
        btn_excel.clicked.connect(self._action_save_results)
        layout.addWidget(btn_excel)

        if tab == "heatmap":
            btn_fig = QPushButton("Export coefficient map")
            btn_fig.clicked.connect(lambda: self._plot_canvas_heatmap.prompt_save_figure(self))
            self._btn_save_heatmap_fig = btn_fig
            self._btn_export_excel_heatmap_tab = btn_excel
        elif tab == "network":
            btn_fig = QPushButton("Export association network")
            btn_fig.clicked.connect(lambda: self._plot_canvas_network.prompt_save_figure(self))
            self._btn_save_network_fig = btn_fig
            self._btn_export_excel_network_tab = btn_excel
        elif tab == "radar":
            btn_fig = QPushButton("Export sample profiles")
            btn_fig.clicked.connect(lambda: self._radar_widget.prompt_save_figure(self))
            self._btn_save_radar_fig = btn_fig
            self._btn_export_excel_radar_tab = btn_excel
        else:
            btn_fig = QPushButton("Export GRG ranking")
            btn_fig.clicked.connect(lambda: self._plot_canvas_grg.prompt_save_figure(self))
            self._btn_save_grg_fig = btn_fig
            self._btn_export_excel = btn_excel

        btn_fig.setEnabled(False)
        btn_fig.setFixedHeight(28)
        layout.addWidget(btn_fig)
        return bar

    def _connect_signals(self) -> None:
        self._config_panel.dataset_loaded.connect(self._on_dataset_loaded)
        self._config_panel.run_requested.connect(self._on_run_requested)
        self._config_panel.status_message.connect(self._status_bar.showMessage)

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
                f"Preview shows the first {_PREVIEW_ROW_LIMIT:,} rows; all {len(dataframe):,} rows are used for analysis."
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
            figure = build_grg_bar_chart(
                result.grg_series,
                title=f"GRG ranking — {ref_col}",
            )
            self._plot_canvas_grg.display_figure(figure)
            self._btn_save_grg_fig.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self._plot_canvas_grg.clear(f"GRG chart failed:\n{exc}")
            self._btn_save_grg_fig.setEnabled(False)
            logger.exception("GRG chart failed: %s", exc)

    def _render_heatmap(self, result: GRAResult, ref_col: str) -> None:
        n_rows, n_cols = result.coefficient_df.shape
        n_cells = n_rows * n_cols
        if n_cells > _HEATMAP_MAX_CELLS:
            self._plot_canvas_heatmap.clear(
                f"Coefficient map omitted for responsiveness.\n"
                f"Matrix size: {n_rows:,} × {n_cols:,} = {n_cells:,} cells.\n"
                "The complete coefficient matrix remains available in Excel."
            )
            self._btn_save_heatmap_fig.setEnabled(False)
            return
        try:
            figure = build_coefficient_heatmap(
                result.coefficient_df,
                title=f"Grey relational coefficients — {ref_col}",
            )
            self._plot_canvas_heatmap.display_figure(figure)
            self._btn_save_heatmap_fig.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self._plot_canvas_heatmap.clear(f"Coefficient map failed:\n{exc}")
            self._btn_save_heatmap_fig.setEnabled(False)
            logger.exception("Coefficient map failed: %s", exc)

    def _render_network(
        self,
        result: GRAResult,
        ref_col: str,
        grg_dict: dict[str, float],
    ) -> None:
        if len(grg_dict) > _NETWORK_MAX_FACTORS:
            top_scores = (
                result.grg_series.sort_values(ascending=False, kind="mergesort")
                .head(_NETWORK_MAX_FACTORS)
                .to_dict()
            )
            self._status_bar.showMessage(
                f"Association network displays the top {_NETWORK_MAX_FACTORS} factors for legibility."
            )
        else:
            top_scores = grg_dict
        try:
            figure = plot_network_diagram(
                target_name=ref_col,
                grg_scores=top_scores,
                title=f"GRG association network — {ref_col}",
            )
            self._plot_canvas_network.display_figure(figure)
            self._btn_save_network_fig.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self._plot_canvas_network.clear(f"Association network failed:\n{exc}")
            self._btn_save_network_fig.setEnabled(False)
            logger.exception("Association network failed: %s", exc)

    def _render_radar(self, result: GRAResult, ref_col: str, comp_cols: list[str]) -> None:
        try:
            norm_df = result.normalised_df
            available_comp = [column for column in comp_cols if column in norm_df.columns]
            sample_df = norm_df.head(_RADAR_MAX_SAMPLES)
            sample_ids = [str(index) for index in sample_df.index]
            data_dict = {
                sample_id: sample_df.iloc[idx][available_comp].astype(float).tolist()
                for idx, sample_id in enumerate(sample_ids)
            }
            title = f"Normalised sample profiles — {ref_col}"
            if len(norm_df) > _RADAR_MAX_SAMPLES:
                title += f" (first {_RADAR_MAX_SAMPLES})"
            self._radar_widget.plot(available_comp, data_dict, title)
            self._btn_save_radar_fig.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self._radar_widget.clear()
            self._btn_save_radar_fig.setEnabled(False)
            logger.exception("Sample profile plot failed: %s", exc)

    def _on_worker_error(self, message: str) -> None:
        self._analysis_failed = True
        QMessageBox.critical(self, "Analysis Error", message)
        self._status_bar.showMessage("Analysis failed — see error dialog.")
        logger.warning("Worker error: %s", message)

    def _on_heatmap_cell_hovered(self, row_label: str, col_label: str, value: float) -> None:
        self._status_bar.showMessage(
            f"Sample: {row_label} · Factor: {col_label} · ξ = {value:.4f}"
        )

    def _on_worker_finished(self) -> None:
        elapsed_ms = self._run_timer.elapsed() if self._run_timer.isValid() else 0
        elapsed = f"{elapsed_ms / 1000:.2f} s" if elapsed_ms > 0 else "N/A"
        self._worker_running = False
        self._worker = None
        self._config_panel.set_running_state(False)
        self._progress_bar.setVisible(False)

        if self._analysis_failed:
            self._status_bar.showMessage(f"Analysis failed · elapsed {elapsed}.")
        elif self._last_result is not None:
            quality = self._last_result.data_quality
            self._status_bar.showMessage(
                f"Analysis complete · {quality.retained_rows}/{quality.original_rows} rows retained · "
                f"elapsed {elapsed} · publication export ready."
            )
        else:
            self._status_bar.showMessage(f"Analysis complete · elapsed {elapsed}.")

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
            self._status_bar.showMessage("No cells selected.")
            return

        cells = {
            (index.row(), index.column()): str(
                model.data(index, Qt.ItemDataRole.DisplayRole) or ""
            )
            for index in selection
        }
        rows = sorted({row for row, _ in cells})
        cols = sorted({col for _, col in cells})
        headers = [
            str(model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or "")
            for col in cols
        ]
        lines = ["\t".join(headers)]
        for row in rows:
            lines.append("\t".join(cells.get((row, col), "") for col in cols))
        QApplication.clipboard().setText("\n".join(lines))
        self._status_bar.showMessage(f"Copied {len(cells)} cell(s).")

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
            lines.append(
                "\t".join(
                    str(model.data(model.index(row, col), Qt.ItemDataRole.DisplayRole) or "")
                    for col in range(n_cols)
                )
            )
        QApplication.clipboard().setText("\n".join(lines))
        self._status_bar.showMessage(f"Copied preview: {n_rows} rows × {n_cols} columns.")

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

    def _action_load_dataset(self) -> None:
        self._config_panel._on_load_clicked()

    def _action_save_results(self) -> None:
        if self._last_result is None:
            QMessageBox.information(self, "No Results", "Run an analysis before exporting results.")
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results to Excel",
            "gra_results.xlsx",
            "Excel Workbook (*.xlsx)",
        )
        if not path_str:
            return
        try:
            saved = save_results_to_excel(self._last_result, path_str)
            QMessageBox.information(
                self,
                "Export Successful",
                f"Results exported to:\n{saved}\n\n"
                "Workbook sheets:\n"
                "  1. GRG Ranking\n"
                "  2. Normalised Sequences\n"
                "  3. Delta Matrix\n"
                "  4. Xi Coefficient Matrix\n"
                "  5. Analysis Config\n"
                "  6. Data Quality",
            )
            self._status_bar.showMessage(f"Results saved: {saved.name}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export Failed", f"Could not save results:\n{exc}")
            logger.exception("Excel export failed.")

    def _action_show_about(self) -> None:
        QMessageBox.about(
            self,
            "About GRA-MicroAnalyzer",
            "<b>GRA-MicroAnalyzer</b> v1.1.0<br><br>"
            "Grey Relational Analysis for Microstructure–Property Association<br>"
            "Publication-oriented figures for materials research.<br><br>"
            "Vector export: SVG / PDF · Raster export: PNG 600 dpi.<br><br>"
            "GRA quantifies association; it does not establish causality.",
        )

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
